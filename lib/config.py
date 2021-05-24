# I2C pins
SCL_PIN = 22   # D22
SDA_PIN = 21   # D21

# Error led pin
LED_PIN = 2    # onboard led
LED_ON = 0     # inverse logic     
LED_OFF = 1

# Debug (LOW for debugging)
DEBUG_PIN = 5  # D5

# temperature units (Fahrenheit or Celsius)
FAHRENHEIT = False

# pages display
PAGES = ["Date Time", "Currently", "Forecast", "Sensors #1", "Sensors #2"]

# localtime data
TIMEZONE = 1                    # UTC+1 hour
DAYLIGHT_SAVING_TIME = True     # +1 hour between last sunday of March 2AM and last sunday of October 3AM

# interval between measurements (seconds)
INTERVAL = 900

# wifi credentials
SSID = "<Your network SSID>"
PASS = "<Your network password>"
MAX_TRIES = 20

# OpenWeather service
OPENWEATHER_API = "<Your OpenWeather API key>"
OPENWEATHER_CITY = "<Your OpenWeather City>,<2-letter country code>"      
OPENWEATHER_URL1 = "https://api.openweathermap.org/data/2.5/weather?q={city}&appid={api}"
OPENWEATHER_URL2 = "https://api.openweathermap.org/data/2.5/onecall?lat={lat}&lon={lon}&exclude={excl}&appid={api}"

# ThingSpeak service
THINGSPEAK_WRITE_API = "<Your ThingSpeak Write API key>"
THINGSPEAK_READ_API = "<Your ThingSpeak Read API key>"
THINGSPEAK_URL = "https://api.thingspeak.com/update?api_key={api}&field1={temp}&field2={hum}&field3={lum}&field4={pres}"
