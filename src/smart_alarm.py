"""
This module is a program that simulates a Smart Alarm as a Web Sever.
"""
import os
from datetime import datetime, timedelta
import calendar
import sched
import time
import json
import threading
import logging.config
import pyttsx3
import requests
from flask import Flask, render_template, request, redirect, url_for,\
    flash

alarms = []
notifications = []
scheduler = sched.scheduler(time.time, time.sleep)

app = Flask(__name__)

# checks if the 'log' directory exists
try:
    os.mkdir("log")
except:
    print("")

logging.config.fileConfig('logging.conf',
                          disable_existing_loggers=False)

# creating logger
errorLogger = logging.getLogger('smartAlarmLogs')
eventLogger = logging.getLogger('smartAlarmEventsLog')
logging.info("STARTED LOG")

def save_to_log(array: list) -> list:
    """
    Only save certain elements to the event log. Such as the date_time,
    event name and event period.
    :param array: a list where certain data is collected from.
    :return new_array: contains a json formatted list.
    """
    new_array = []
    for col in array:
        temp = []
        for row in range(3):
            temp.append(col[row])
        # stores to new_array as json format
        new_array.append({"date_time": temp[0], "event_name": temp[1],
                          "event_period": temp[2]})
    return new_array

def get_last_line(fname: str):
    """
    This gets the last late in a file.
    :param fname: a string informing the file name.
    :return:
    """
    errorLogger.debug("GET LAST LINE: %s", fname)
    # check if the file exists
    try:
        file = open(fname, 'r')
    except IOError:
        errorLogger.error("Failed to to read log file %s", fname)
        return None
    else:
        with file:
            lines = file.read().splitlines()
            if lines:
                # last line in the file
                return lines[-1]
            return None

def restore_from_log():
    """
    This retrieve the information from log file as json format.
    :return:
    """
    errorLogger.debug("RESTORE FROM LOG")
    log_file_name = get_config("sys_log_file")
    last_line = get_last_line(log_file_name)
    # check if the log file is empty
    if last_line:
        # using '@' as a key to split the string
        split_data = last_line.split("@")

        if len(split_data) <= 1:
            errorLogger.error("Event(s) has not found in the system "
                              "log: %s", last_line)
            return

        events_line = split_data[1].replace("\'", "\"")
        # converts it to json format
        events = json.loads(events_line)

        # recovering data from the log file and assigning it to the
        # alarm.
        for element in events:
            date_time = element["date_time"]
            date_time_obj = datetime.strptime(date_time, "%d/%m/%Y "
                                                         "%H:%M")
            event_name = element["event_name"]
            event_period = element["event_period"]

            # check the event isn't expired
            if event_period != "Once" or date_time_obj >= \
                    datetime.now():
                errorLogger.info("Restoring Alarm Notification "
                                 "Schedule(s)")
                time_delay = time_difference(date_time_obj)

                event_sched = scheduler.enter(
                    time_delay, 1, set_notification,
                    argument=(date_time, event_name, event_period))

                alarms.append([date_time, event_name, event_period,
                               event_sched])

                errorLogger.info("Alarm of Event %s has been Restored"
                                 " successfully.", event_name)
            else:
                errorLogger.warning("Alarm of Event %s has expired due"
                                    " to only being repeated once.",
                                    event_name)
    else:
        errorLogger.warning("System log is empty")

def get_event(event_name: str) -> list:
    """
    This retrieve the element in the list alarms by the event_name.
    :param event_name: a string that is unique, which has been set by
     the user.
    :return element: a list of the element in the array ALARMS.
    :return []: an empty list.
    """
    errorLogger.debug("GET EVENT: %s", event_name)
    for element in alarms:
        if element[1] == event_name:
            return element
    return []

def time_difference(date_time: datetime) -> int:
    """
    Calculate the time difference between the alarm time and the
    current time in seconds.
    :param date_time: a datetime used to calculate the time difference.
    :return remaining_time: an integer representing the remaining time.
    """
    errorLogger.debug("TIME DIFFERENT: %s", date_time)
    # calculating the time different in seconds
    remaining_time = (date_time - datetime.now()).total_seconds()
    errorLogger.debug("Remaining Time from NOW: %d",
                      int(remaining_time))
    # returning the time different in seconds as a whole number
    return int(remaining_time)

def add_one_month(date_time: datetime) -> datetime:
    """
    Adding one month to a datetime.
    :param date_time: a datetime used to add one month to it.
    :return date_time.replace(year, month, day): a datetime with one
    month added.
    """
    errorLogger.debug("ADD ONE MONTH: %s", date_time)
    new_year = date_time.year
    new_month = date_time.month + 1
    # check if the month is valid
    if new_month > 12:
        new_year += 1
        new_month -= 12

    last_day_of_month = calendar.monthrange(new_year, new_month)[1]
    new_day = min(date_time.day, last_day_of_month)

    return date_time.replace(year=new_year, month=new_month,
                             day=new_day)

def add_days(event_period: str, date_time: str) -> datetime:
    """
    Adding days depending on alarm repeats set by the user.
    :param event_period: a string informing how often the repeat needs
     to be.
    :param date_time: a datetime containing the date-time, which needed
     to be repeated.
    :return: a datetime with added days for repeats.
    """
    errorLogger.debug("ADD DAYS: %s, %s", event_period, date_time)
    date_time = datetime.strptime(date_time, "%d/%m/%Y %H:%M")
    if event_period == "Everyday":
        # add 1 day
        return date_time + timedelta(days=1)
    elif event_period == "Every Week":
        # add 1 week
        return date_time + timedelta(weeks=1)
    elif event_period == "Every Month":
        # add 1 month
        return add_one_month(date_time)
    elif event_period == "Every Year":
        # add 1 year
        return date_time.replace(year=date_time.year + 1)

def reschedule(date_time: str, event_name: str, event_period: str):
    """
    Checks whether or not the alarm needs to be rescheduled.
    :param date_time: a datetime containing the date and time set by
     the user.
    :param event_name: a string representing the event name.
    :param event_period: a string representing the frequency of the
     alarm.
    """
    errorLogger.debug("RESCHEDULE: %s, %s, %s", date_time, event_name,
                      event_period)
    event = get_event(event_name)
    if event:
        # checking weather or not the event needs to be rescheduled
        if event_period == "Once":
            alarms.remove(event)
        else:
            alarms.remove(event)
            new_date_time = add_days(event_period, date_time)
            temp_delay = time_difference(new_date_time)

            errorLogger.info("Add new schedule event")
            # rescheduling
            event_sched = scheduler.enter(
                temp_delay, 1, set_notification,
                argument=(str(new_date_time.strftime("%d/%m/%Y %H:%M")),
                          event_name, event_period))

            alarms.append([str(new_date_time.strftime("%d/%m/%Y %H:%M")),
                           event_name, event_period, event_sched])

def set_notification(date_time: str, event_name: str, event_period: str):
    """
    This inform the user that the alarm has went off by setting a
     notification.
    :param date_time: a datetime containing the date and time set by
     the user.
    :param event_name: a string representing the event name.
    :param event_period: a string representing the frequency of the
     alarm.
    """
    errorLogger.debug("SET NOTIFICATION: %s, %s, %s", date_time,
                      event_name, event_period)

    try:
        # text-to-speech
        errorLogger.info("Alarm! Alarm! Alarm!")
        engine = pyttsx3.init()
        engine.say("Alarm! Alarm! Alarm!")
        engine.say("An alarm for " + event_name)
        engine.say("at " + date_time)
        engine.runAndWait()
        engine.stop()
    except:
        errorLogger.error("pyttsx3 only supports Windows environment")

    notifications.append([date_time, event_name, event_period])

    reschedule(date_time, event_name, event_period)

def scheduler_event():
    """
    Starts the scheduler thread, which will run parallel to flask.
    """
    errorLogger.debug("SCHEDULER EVENT")
    errorLogger.info("Start alarm scheduler events")

    while True:
        try:
        # prevents the program from getting blocked and waiting there.
            scheduler.run(blocking=False)
            time.sleep(0.1)
        except:
            errorLogger.error("Error in scheduler Thread")

def weather_api() -> json:
    """
    This retrieve the weather api as a json format.
    :return weather: a json file to be accessed in the html.
    """
    errorLogger.debug("WEATHER API")
    errorLogger.info("Getting Weather Data by URL")
    # weather api url
    weather_url = "http://api.openweathermap.org/data/2.5/weather?q=" \
                  "{}&units=metric&appid="
    weather_url += get_config("weather")
    city = "Exeter"

    # gets the weather api as json format
    weather_request = requests.get(weather_url.format(city)).json()

    # storing the variable 'weather' as json
    weather = {
        "city": city,
        "temperature": weather_request["main"]["temp"],
        "description": weather_request["weather"][0]["description"],
        "icon": weather_request["weather"][0]["icon"],
    }
    return weather

def news_api() -> json:
    """
    This retrieve the news api as a json format.
    :return news: a json file to be accessed in the html.
    """
    errorLogger.debug("NEWS API")
    errorLogger.info("Getting News Data by URL")
    # news api url
    news_url = "https://newsapi.org/v2/top-headlines?sources=" \
               "bbc-news&apiKey="
    news_url += get_config("news")

    # gets the news api as json format
    news_request = requests.get(news_url).json()

    # storing the variable 'news' as json
    news = {
        "url": news_request["articles"][0]["url"],
        "image": news_request["articles"][0]["urlToImage"],
        "title": news_request["articles"][0]["title"],
        "description": news_request["articles"][0]["description"],
        "date": news_request["articles"][0]["publishedAt"],
    }
    return news

def get_config(name: str):
    """
    Gets the information in the config file.
    :param name: a string used to search for the value representing
     it.
    """
    errorLogger.debug("GET CONFIG: %s", name)
    # openning the config.json file
    try:
        config_file = open('config.json')

    except IOError:
        errorLogger.error("Failed to read config file %s", name)
        return None
    else:
        with config_file:
            # storing it to a variable
            data = json.load(config_file)

            if name == "weather":
                return data["weather_api_key"]
            elif name == "news":
                return data["news_api_key"]
            else:
                return data[name]

@app.route('/', methods=['GET'])
def root() -> redirect:
    """
    This function will run at the localhost when it is being started
     up.
    :return: redirect to the home method.
    """
    errorLogger.debug("ROOT")
    return redirect(url_for('home'))

@app.route('/home', methods=['GET'])
def home() -> render_template:
    """
    Initialise the home page for the web sever.
    :return:
    """
    errorLogger.debug("HOME")
    weather = weather_api()
    news = news_api()

    # sorted depending on time
    alarms.sort(key=lambda x: datetime.strptime(x[0],
                                                '%d/%m/%Y %H:%M'))
    errorLogger.info("Alarms list has been sorted by date time")
    errorLogger.debug(alarms)

    return render_template(get_config("home_page"), weather=weather,
                           news=news, ALARMS=alarms,
                           NOTIFICATIONS=notifications)

@app.route('/addAlarm', methods=['POST'])
def add_alarm() -> redirect:
    """
    Adding alarm to the alarms list, which was set by the user.
    :return:
    """
    errorLogger.debug("ADDING ALARM")
    date_time = request.form.get("date").replace('T', ' ')
    date_time = datetime.strptime(date_time, "%Y-%m-%d %H:%M")
    event_name = request.form.get("event_name")
    event_period = request.form.get("event_period")

    errorLogger.debug("ADDING ALARM: date_time: %s, event_name: %s, "
                      "event_period: %s", date_time, event_name,
                      event_period)

    # validating that the alarm is set to a future date.
    if date_time <= datetime.now():
        flash("Alarm of Event " + event_name + " at "
              + str(date_time.strftime("%d/%m/%Y %H:%M"))
              + " is in past!", 'error')
        errorLogger.warning("Alarm of Event %s at %s is in past.",
                            event_name,
                            str(date_time.strftime("%d/%m/%Y %H:%M")))
        return redirect(url_for('home'))

    alarm = get_event(event_name)
    if not alarm:
        errorLogger.info("Create Schedule for an event %s", event_name)
        time_delay = time_difference(date_time)

        event_sched = scheduler.enter(
            time_delay, 1, set_notification,
            argument=(str(date_time.strftime("%d/%m/%Y %H:%M")),
                      event_name, event_period))

        alarms.append([str(date_time.strftime("%d/%m/%Y %H:%M")),
                       event_name, event_period, event_sched])

        # Save alarms list into system log
        eventLogger.critical("Alarms list : @%s", save_to_log(alarms))

        errorLogger.info("Event change has been captured and recorded"
                         " into"
                         " system log for CREATE action.")

        flash("Alarm of Event " + event_name + " has been Created "
                                               "successfully",
              'success')
        errorLogger.info("Alarm of Event %s has been Created "
                         "successfully.", event_name)
    else:
        flash("Alarm of Event " + event_name + " already exists",
              'error')
        errorLogger.warning("Alarm of Event %s already exists.",
                            event_name)

    return redirect(url_for('home'))

@app.route('/editAlarm', methods=['POST'])
def edit_alarm() -> render_template:
    """
    Editing alarm.
    :return:
    """
    errorLogger.debug("EDITING ALARM")
    weather = weather_api()
    news = news_api()

    temp_date = request.form.get("date")
    temp_date = datetime.strptime(temp_date, "%d/%m/%Y %H:%M")
    temp_date = str(temp_date.strftime("%Y-%m-%dT%H:%M"))
    temp_event_name = request.form.get("event_name")
    temp_event_period = request.form.get("event_period")

    errorLogger.debug("EDITING ALARM (Before): date_time:%s, "
                      "event_name:%s, event_period:%s", temp_date,
                      temp_event_name, temp_event_period)

    return render_template(get_config("edit_page"), weather=weather,
                           news=news, event_period=temp_event_period,
                           alarm=temp_date, event_name=temp_event_name)

@app.route('/updateAlarm/<string:event_id>', methods=['POST'])
def update_alarm(event_id: str) -> redirect:
    """
    Updating alarm.
    :param event_id: a string to indicate the id of the event.
    :return:
    """
    errorLogger.debug("UPDATING ALARM")
    temp_alarm = []

    event_name = request.form.get("event_name")
    date_time = request.form.get("date").replace('T', ' ')
    date_time = datetime.strptime(date_time, "%Y-%m-%d %H:%M")
    event_period = request.form.get("event_period")

    errorLogger.debug("UPDATING ALARM (After): date_time:%s, "
                      "event_name:%s, event_period:%s", date_time,
                      event_name, event_period)
    # checks the date hasn't expired
    if date_time <= datetime.now():
        flash("Alarm of Event " + event_name + " at "
              + str(date_time.strftime("%d/%m/%Y %H:%M"))
              + " is in past!", 'error')

        errorLogger.warning("Alarm of Event %s at %s is in past.",
                            event_name,
                            str(date_time.strftime("%d/%m/%Y %H:%M")))

        return redirect(url_for('home'))

    old_event_name = event_id
    # checks if the event_name is unique
    if event_name != old_event_name:
        alarm = get_event(event_name)
        if alarm:
            flash("Alarm of Event " + event_name
                  + " already exists when event change from "
                  + old_event_name + "", 'error')

            errorLogger.warning("Alarm of Event %s already exists "
                                "when change event change from %s.",
                                event_name, old_event_name)

            return redirect(url_for('home'))

    errorLogger.info("Updating Schedule for an event %s", event_name)
    alarm = get_event(old_event_name)
    event_sched = alarm[3]

    # cancelling event
    errorLogger.debug("Cancelling Schedule")
    scheduler.cancel(event_sched)
    alarms.remove(alarm)

    # updating event
    errorLogger.debug("Updating Schedule")
    time_delay = time_difference(date_time)
    event_sched = scheduler.enter(
        time_delay, 1, set_notification,
        argument=(str(date_time.strftime("%d/%m/%Y %H:%M")),
                  event_name, event_period))

    temp_alarm.append(str(date_time.strftime("%d/%m/%Y %H:%M")))
    temp_alarm.append(event_name)
    temp_alarm.append(event_period)
    temp_alarm.append(event_sched)

    alarms.append(temp_alarm)

    # Save alarms list into system log
    eventLogger.critical("Alarms list : @%s", save_to_log(alarms))
    errorLogger.info("Event change has been captured and recorded into"
                     " system log for UPDATE action.")

    flash("Alarm of Event " + event_name + " has been updated "
                                           "successfully", 'success')
    errorLogger.info("Alarm of Event %s has been updated "
                     "successfully.", event_name)

    return redirect(url_for('home'))

@app.route('/deleteAlarm/<string:event_id>', methods=['POST'])
def delete_alarm(event_id: str) -> redirect:
    """
    Deleting alarm.
    :param event_id: a string to indicate the id of the event.
    :return:
    """
    errorLogger.debug("DELETE ALARM")
    alarm = get_event(event_id)
    if alarm:
        event_sched = alarm[3]
        # deleting event
        errorLogger.debug("Cancelling Schedule")
        scheduler.cancel(event_sched)
        alarms.remove(alarm)

        # Save alarms list into system log
        eventLogger.critical("Alarms list : @%s", save_to_log(alarms))
        errorLogger.info("Event change has been captured and recorded "
                         "into system log for DELETE action.")

        flash("Alarm of Event " + event_id + " has been removed "
                                             "successfully", 'success')
        errorLogger.info("Alarm of Event %s has been removed "
                         "successfully.", event_id)
    else:
        flash("Alarm of Event " + event_id
              + " is not exists for remove", 'error')
        errorLogger.warning("Alarm of Event %s is not exists for "
                            "remove.", event_id)

    return redirect(url_for('home'))

if __name__ == '__main__':

    thread = threading.Thread(target=scheduler_event)
    thread.setDaemon(True)
    thread.start()

    app.secret_key = 'super secret key'
    app.config['SESSION_TYPE'] = 'filesystem'
    restore_from_log()
    app.run()
