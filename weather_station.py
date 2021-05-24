'''
    Weather Station (c)2021 Effevee
    
    A Weather Station with OLED display and Temperature, Humidity, Atmosphetic Pressure and Light sensor.
    Weather predictons are fetched from OpenWeatherMap.org, sensor readings are shown on OLED display and uploaded to the ThingSpeak IoT platform.
    
    Hardware : - DOIT ESP32 DEVKit v1 dev board
               - AM2320 temperature and humidity sensor board
               - BMP180 temperature, pressure and altitude sensor board
               - BH1750FVI light sensor board
               - OLED 0.96" SSD1306 128x64 Yellow & Blue display
 
    Software : MicroPython code developped by Effevee
    
    Wiring :    ESP32     AM2320     BMP180     BH1750FVI     OLED     Debug 
                Pin GPIO    Pin        Pin         Pin        Pin       ON
                --------   -----     ------     ---------     ----     -----
                3V           1         VIN         VCC        VCC
                GND          3         GND         GND        GND
                D22  22      4         SCL         SCL        SCL
                D21  21      2         SDA         SDA        SDA
                D5   5                                                  GND
                   
    More details on https://github.com/effevee/weather_station
    
'''

####################################################################################
# Libraries
####################################################################################

from machine import Pin, SoftI2C, RTC, deepsleep
from ssd1306 import SSD1306_I2C
import network
import ntptime
import utime
import config
import sys
import urequests
import framebuf
import freesans20
from writer_minimal import Writer
from am2320 import AM2320
from bmp180 import BMP180
from bh1750 import BH1750

####################################################################################
# Error routine
####################################################################################

def show_error():
    ''' visual display of error condition - flashing onboard LED '''
    
    # led pin object
    led = Pin(config.LED_PIN, Pin.OUT)
    
    # flash 3 times
    for i in range(3):
        led.value(config.LED_ON)
        utime.sleep(0.5)
        led.value(config.LED_OFF)
        utime.sleep(0.5)
    

####################################################################################
# Check debug on
####################################################################################

def debug_on():
    ''' check if debugging is on - debug pin LOW '''
    
    # debug pin object
    debug = Pin(config.DEBUG_PIN, Pin.IN, Pin.PULL_UP)
    
    # check debug pin
    if debug.value() == 0:
        # print('Debug mode detected.')
        return True
    
    return False


####################################################################################
# Connect to Wifi
####################################################################################

def connect_wifi():
    ''' connect the µcontroller to the local wifi network '''
    
    # disable AP mode of µcontroller
    ap_if = network.WLAN(network.AP_IF)
    ap_if.active(False)
    
    # enable STAtion mode of µcontroller
    sta_if = network.WLAN(network.STA_IF) 

    # if no wifi connection exist
    if not sta_if.isconnected():
        
        # debug message
        print('connecting to WiFi network...')
        
        # activate wifi station
        sta_if.active(True)
        
        # try to connect to the wifi network
        sta_if.connect(config.SSID, config.PASS)  
        
        # keep trying for a number of times
        tries = 0
        while not sta_if.isconnected() and tries < config.MAX_TRIES:  
            
            # show progress
            print('.', end='')
            
            # wait
            utime.sleep(1)
            
            # update counter
            tries += 1

    # show network status 
    if sta_if.isconnected():
        print('')
        print('connected to {} network with ip address {}' .format(config.SSID, sta_if.ifconfig()[0]))

    else:
        print('')
        print('no connection to {} network' .format(config.SSID))
        raise RuntimeError('WiFi connection failed')


####################################################################################
# Synchronize RTC on µcontroller to local time
####################################################################################

def synchronize_rtc():
    ''' Synchronize the date and time on the µcontroller to local time.
        1. Connect to NTP server on the internet to set UTC time on RTC
        2. Correct according to Timezone and Daylight Saving Time settings
            TZ  : number of hours (positive or negative) difference to UTC
            DST : Daylight Savings Time (true or false)
                if True : one hour is added from last Sunday of March 2AM till
                          last Sunday of October 3AM '''
    
    # rtc object
    rtc = RTC()
    
    # localtime tuple
    # (year, month, mday, hour, minute, second, weekday, yearday)
    #  20xx  1-12   1-31  0-23   0-59    0-59    0-6      1-366
    tm = utime.localtime()

    # we have not synchronized before if current year is 2000 (default year)
    if tm[0] == 2000:
        
        # debug message
        print('Synchronize RTC to local time')
        if debug_on():
            print('Current datetime: {}' .format(tm))
            print('Synchronize with NTP server...')      
        
        # set RTC to UTC with NTP server       
        ntptime.settime()

        # debug message
        if debug_on():
            print('NTP correction:   {}' .format(utime.localtime()))

        # time zone correction
        # utime localtime -> (year, month, mday, hour, minute, second, weekday, yearday)
        tm = utime.localtime(utime.time() + (config.TIMEZONE * 3600))
        # rtc datetime    -> (year, month, mday, weekday, hour, minute, second, µseconds)
        rtc.datetime((tm[0], tm[1], tm[2], tm[6], tm[3], tm[4], tm[5], 0))
    
        # debug message
        if debug_on():
            print('TZ correction:    {}' .format(utime.localtime()))
    
        # Daylight Savings Time correction
        if config.DAYLIGHT_SAVING_TIME:
                
            # current year
            year = utime.localtime()[0]
            
            # last Sunday March
            HHMarch = utime.mktime((year, 3, (31-(int(5*year/4+4))%7), 2, 0, 0, 0, 0))
            
            # last Sunday October
            HHOctober = utime.mktime((year, 10, (31-(int(5*year/4+1))%7), 3, 0, 0, 0, 0))
            
            # current time
            curtime = utime.time()
            
            # correct local time
            if (curtime >= HHMarch) and (curtime < HHOctober):

                # utime localtime -> (year, month, mday, hour, minute, second, weekday, yearday)
                tm = utime.localtime(curtime + 3600)
                
                # rtc datetime    -> (year, month, mday, weekday, hour, minute, second, µseconds)
                rtc.datetime((tm[0], tm[1], tm[2], tm[6], tm[3], tm[4], tm[5], 0))
                
            # debug message
            if debug_on():
                print('DST correction:   {}' .format(utime.localtime()))
                
            
####################################################################################
# Get weather data from OpenWeather.org
####################################################################################

def get_weather_data():
    ''' get current weather data and forcasts from OpenWeather.org.
        return results in list with following data for each day :
        - 'temp' : current/day temperature
        - 'hum' : humidity
        - 'pres' : pressure
        - 'icon' : weather icon
        - 'report' : weather text
        The dictionary contains 4 entries : current weather and forcast for the next 3 days'''
    
    # debug message
    print('Invoking OpenWeather URL1 webhook')
    
    # webhook url
    url = config.OPENWEATHER_URL1.format(city=config.OPENWEATHER_CITY, api=config.OPENWEATHER_API)
    
    # send GET request
    response = urequests.get(url)
    
    # evaluate response
    if response.status_code < 400:
        print('Webhook OpenWeather URL1 success')

    else:
        print('Webhook OpenWeather URL1 failed')
        raise RuntimeError('Webhook OpenWeather URL1 failed')
    
    # get the data in json format
    today = response.json()
    
    # debug message
    if debug_on():
        print('OpenWeather URL1 data')
        print(today)

    # extract data from OpenWeather dictionary
    temp = temperature_2_unit(today['main']['temp'] - 273.15)  # openweather temperatures in Kelvin 
    hum = today['main']['humidity'] 
    pres = today['main']['pressure']
    icon = today['weather'][0]['icon']
    report = today['weather'][0]['description']
    
    # save data in return list
    owdata = []
    owdata.append({'temp': temp, 'hum': hum, 'pres': pres, 'icon': icon, 'report': report})
    
    # get longitude and latitude of city
    longitude = today['coord']['lon']
    latitude = today['coord']['lat']
    
    # debug message
    print('Invoking OpenWeather URL2 webhook')
    
    # webhook url
    url = config.OPENWEATHER_URL2.format(lat=latitude, lon=longitude, excl='current,minutely,hourly,alerts', api=config.OPENWEATHER_API)
    
    # send GET request
    response = urequests.get(url)
    
    # evaluate response
    if response.status_code < 400:
        print('Webhook OpenWeather URL2 success')

    else:
        print('Webhook OpenWeather URL2 failed')
        raise RuntimeError('Webhook OpenWeather URL1 failed')
    
    # get the data in json format
    forecast = response.json()
    
    # debug message
    if debug_on():
        print('OpenWeather URL2 data')
        print(forecast)
    
    # the OpenWeather data contains a list 'daily' of forecasts for today (index 0)
    # and the next 7 days (index 1 to 7). We extract the forecasts for the next 3 days.
    for day in range(1, 4):
        
        # extract data
        temp = temperature_2_unit(forecast['daily'][day]['temp']['day'] - 273.15) 
        hum = forecast['daily'][day]['humidity']
        pres = forecast['daily'][day]['pressure']
        icon = forecast['daily'][day]['weather'][0]['icon']
        report = forecast['daily'][day]['weather'][0]['description']
        
        # save data in return list
        owdata.append({'temp': temp, 'hum': hum, 'pres': pres, 'icon': icon, 'report': report})

    # debug message
    if debug_on():
        print('OpenWeather return data')
        print(owdata)
    
    return owdata
    
    
####################################################################################
# Temperature in Celsium or Fahrenheit
####################################################################################
def temperature_2_unit(celsius):
    ''' convert the temperature in Celsius to Fahrenheit is necessary '''
    
    # convert if necessary
    if config.FAHRENHEIT:
        return celsius * 9 / 5 + 32
    else:
        return celsius
    

####################################################################################
# Get sensor readings
####################################################################################

def get_sensor_readings():
    ''' get readings from all sensors and return them in a list '''
    
    # debug message
    print('Getting sensor readings')
    
    # I2C object
    i2c = SoftI2C(scl=Pin(config.SCL_PIN), sda=Pin(config.SDA_PIN))
    
    # AM2320 temperature and humidity sensor
    am2320 = AM2320(i2c)
    
    # check if AM2320 sensor is detected
    i2c.scan()  # first scan to wake up sensor
    if 92 not in i2c.scan():
        raise RuntimeError('Cannot find AM2320 sensor')
    
    # read AM2320 sensor
    am2320.measure()
    am2320_temp = temperature_2_unit(am2320.temperature())
    am2320_hum = am2320.humidity()
    
    if debug_on():
        print('')
        print('AM2320    T: {:.0f} {} - H: {:.0f} %' .format(am2320_temp, 'F' if config.FAHRENHEIT else 'C', am2320_hum))

    # BMP180 temperature, pressure and altitude sensor
    bmp180 = BMP180(i2c)

    # check if BMP180 sensor is detected
    if 119 not in i2c.scan():
        raise RuntimeError('Cannot find BMP180 sensor')

    # read BMP180 sensor
    bmp180_temp = temperature_2_unit(bmp180.temperature)
    bmp180_pres = bmp180.pressure/100  # values in Pa, divide by 100 for hPa
    bmp180_alt = bmp180.altitude
    
    if debug_on():
        print('BMP180    T: {:.0f} {} - P: {:.0f} hPa - A: {:.0f} m' .format(bmp180_temp, 'F' if config.FAHRENHEIT else 'C', bmp180_pres, bmp180_alt))

    # BH1750FVI light sensor
    bh1750 = BH1750(i2c)
    
    # check if BH1750 sensor is detected
    if 35 not in i2c.scan():
        raise RuntimeError('Cannot find BH1750 sensor')
    
    # read BH1750 sensor
    bh1750_lum = bh1750.luminance(BH1750.ONCE_HIRES_1)
    
    if debug_on():
        print('BH1750FVI L: {:.0f} lux' .format(bh1750_lum))

    return [{'am2320_temp': am2320_temp, 'am2320_hum': am2320_hum, 'bmp180_temp': bmp180_temp, 'bmp180_pres': bmp180_pres, 'bmp180_alt': bmp180_alt, 'bh1750_lum': bh1750_lum}]
    

####################################################################################
# Load PBM image
####################################################################################

def load_pbm_image(filename):
    ''' Load a PBM (Portable Bitmap) image into the framebuffer of the OLED display
        
        Structure of a PBM image :
            P4
            # Description
            <width> <height>
            <binary image data>
        
        1st line = type identifier (P4 = MONO_HLSB, bits are horizontally mapped, with LSB (bit 0) to the left)
        2nd line = description of the image file
        3rd line = width and height of the image file
        4th line = binary data of the image (1 byte = 8 pixels)
        '''
    
    # open pbm image in read binary format
    with open(filename, 'rb') as f:
        
        # ignore identifier and description
        f.readline()
        f.readline()
        
        # extract width and height of image
        width, height = [int(v) for v in f.readline().split()]
        
        # extract image data
        data = bytearray(f.read())
        
    return framebuf.FrameBuffer(data, width, height, framebuf.MONO_HLSB)


####################################################################################
# Update OLED display
####################################################################################

def update_oled_display(ow_data, sensor_data):
    ''' Update the oled display with sensor readings and forecasts '''
    
    DOW = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    
    # debug message
    print('Updating OLED')
    
    # I2C object
    i2c = SoftI2C(scl=Pin(config.SCL_PIN), sda=Pin(config.SDA_PIN))
    
    # check if OLED display is detected
    if 60 not in i2c.scan():
        raise RuntimeError('Cannot find OLED display')
    
    # display object
    display = SSD1306_I2C(128, 64, i2c)
    
    # custom font writer object
    font_writer = Writer(display, freesans20)
    
    # get date & time
    year, month, day, hour, minute, second, dayofweek, dayofyear = utime.localtime()

    # show different pages
    for page in range(len(config.PAGES)):

        # clear oled
        display.fill(0)
        
        # title
        display.text(config.PAGES[page], 0, 0)
        
        # current page
        if page == 0:      # Date & Time
            
            # draw date
            font_writer.set_textpos(20, 4)
            font_writer.printstring('{:02d}/{:02d}/{:04d}'.format(day, month, year))
            
            # draw time
            font_writer.set_textpos(44, 4)
            font_writer.printstring('{}  {:02d}:{:02d}'.format(DOW[dayofweek], hour, minute))
            
        elif page == 1:   # OpenWeather current data

            # extract OpenWeather current data
            temp = ow_data[0]['temp']
            hum = ow_data[0]['hum']
            pres = ow_data[0]['pres']
            icon = ow_data[0]['icon']
            report = ow_data[0]['report']
            
            # load pbm image
            icon_pbm = load_pbm_image('/img/' + icon[:2] + '@2x.pbm')

            # display dayofweek
            display.text('{}' .format(DOW[dayofweek]), 6, 16)

            # display weather icon
            display.blit(icon_pbm, 4, 25)
                        
            # display current data
            display.text('T:{:.0f} {}' .format(temp, 'F' if config.FAHRENHEIT else 'C'), 46, 25)
            display.text('H:{} %' .format(hum), 46, 35)
            display.text('P:{} hPa' .format(pres), 46, 45)
            display.text('{}' .format(report), 0, 55)
            
        elif page == 2:   # OpenWeather forecast data

            # display OpenWeather forecast data for next 3 days
            for day in range(1, 4):
                
                # 3 columns on screen
                col_offset = (day - 1) * 40
                
                # extract Openweather forecast data
                temp = ow_data[day]['temp']
                hum = ow_data[day]['hum']
                pres = ow_data[day]['pres']
                icon = ow_data[day]['icon']
                report = ow_data[day]['report']

                # load pbm image
                icon_pbm = load_pbm_image('/img/' + icon[:2] + '@2x.pbm')
                
                # display dayofweek
                display.text('{}' .format(DOW[(dayofweek + day) % 7]), 6 + col_offset, 16)
                
                # display weather icon
                display.blit(icon_pbm, 4 + col_offset, 25)
                
                # display forecast data
                display.text('{:.0f}{}' .format(temp, 'F' if config.FAHRENHEIT else 'C'), 6 + col_offset, 55)
                
        
        elif page == 3:   # Temperature and humidity
             
            # load pbm images
            temp_pbm = load_pbm_image('/img/temperature.pbm')
            hum_pbm  = load_pbm_image('/img/humidity.pbm')
            
            # draw pbm images
            display.blit(temp_pbm, 4, 20)
            display.blit(hum_pbm, 4, 44)
            
            # extract sensor readings
            temp = sensor_data[0]['am2320_temp']
            hum = sensor_data[0]['am2320_hum']

            # draw readings
            font_writer.set_textpos(20, 24)
            font_writer.printstring('{:.1f} {}' .format(temp, 'F' if config.FAHRENHEIT else 'C'))
            font_writer.set_textpos(44, 24)
            font_writer.printstring('{:.1f} %' .format(hum))
        
        elif page == 4:  # Pressure and luminance
            
            # load pbm images
            press_pbm = load_pbm_image('/img/pressure.pbm')
            lum_pbm  = load_pbm_image('/img/luminance.pbm')
            
            # draw pbm images
            display.blit(press_pbm, 4, 20)
            display.blit(lum_pbm, 4, 44)
            
            # extract sensor readings
            pres = sensor_data[0]['bmp180_pres']
            lum = sensor_data[0]['bh1750_lum']

            # draw readings
            font_writer.set_textpos(20, 24)
            font_writer.printstring('{:.0f} hPa' .format(pres))
            font_writer.set_textpos(44, 24)
            font_writer.printstring('{:.0f} lux' .format(lum))
            
        # show page
        display.show()

        # wait
        utime.sleep(5)
        
    # power off
    display.poweroff()


####################################################################################
# Upload sensor values to ThingSpeak
####################################################################################

def log_sensor_readings(sensor_data):
    ''' upload sensor readings to ThingSpeak '''
    
    # debug message
    print('Invoking ThingSpeak logging webhook')
    
    # extract readings to upload
    temperature = sensor_data[0]['am2320_temp']
    humidity = sensor_data[0]['am2320_hum']
    pressure = sensor_data[0]['bmp180_pres']
    luminance = sensor_data[0]['bh1750_lum']
    
    # webhook url
    url = config.THINGSPEAK_URL.format(api=config.THINGSPEAK_WRITE_API, temp=temperature, hum=humidity, pres=pressure, lum=luminance)
    
    # send GET request
    response = urequests.get(url)
    
    # evaluate response
    if response.status_code < 400:
        print('Webhook ThingSpeak success')

    else:
        print('Webhook ThingSpeak failed')
        raise RuntimeError('Webhook ThingSpeak failed')
    

####################################################################################
# deepsleep to save battery
####################################################################################

def deepsleep_till_next_cycle():
    ''' put the µcontroller into deepsleep to save battery for config.INTERVAL seconds. '''
    
    # debug message
    print('Going into deepsleep for {} seconds...' .format(config.INTERVAL))
    utime.sleep(2)
   
    # goto deepsleep - time in milliseconds !
    deepsleep(config.INTERVAL * 1000)
    
    
####################################################################################
# Main program
####################################################################################

def run():
    ''' main program logic '''
    
    try:
        
        # connect to WiFi network
        connect_wifi()
        
        # Synchronize RTC
        synchronize_rtc()

        # get OpenWeather data
        ow_data = get_weather_data()
        
        # get sensor readings
        sensor_data = get_sensor_readings()
        
        # update OLED display
        update_oled_display(ow_data, sensor_data)
        
        # upload sensor readings to ThingSpeak
        log_sensor_readings(sensor_data)

    except Exception as exc:
        sys.print_exception(exc)
        show_error()
    
    # goto deepsleep if not in debugging mode
    if not debug_on():
        deepsleep_till_next_cycle()
        

run()
        
    

