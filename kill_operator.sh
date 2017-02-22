#!/bin/sh

ps -ef | grep python | grep itsbox | grep Startup.py | awk '{print $2}' | xargs kill -9
