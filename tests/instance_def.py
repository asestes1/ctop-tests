import typing
import os
import sys
import datetime

sys.path.insert(0, sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))))
import bctop.allocations as bctop


def small_instance() -> typing.Dict:
    starttime = datetime.datetime(2010, 1, 1, 9, 00)

    slots = set()
    for i in range(0, 5):
        slots.add(bctop.Slot(sid=i, time=starttime + datetime.timedelta(minutes=60 + i * 15)))

    flight1 = bctop.Flight(fid=1,
                           deptime=starttime,
                           flight_duration=datetime.timedelta(minutes=56),
                           rtc=datetime.timedelta(minutes=5),
                           airline="B",
                           weight=1)

    flight2 = bctop.Flight(fid=2,
                           deptime=starttime + datetime.timedelta(minutes=30),
                           flight_duration=datetime.timedelta(minutes=27),
                           rtc=datetime.timedelta(minutes=16),
                           airline="A",
                           weight=100)
    flight3 = bctop.Flight(fid=3,
                           deptime=starttime + datetime.timedelta(minutes=15),
                           flight_duration=datetime.timedelta(minutes=43),
                           rtc=datetime.timedelta(minutes=35),
                           airline="B",
                           weight=1)
    flight4 = bctop.Flight(fid=4,
                           deptime=starttime + datetime.timedelta(minutes=60),
                           flight_duration=datetime.timedelta(minutes=13),
                           rtc=datetime.timedelta(minutes=30),
                           airline="A",
                           weight=100)
    flight5 = bctop.Flight(fid=5,
                           deptime=starttime + datetime.timedelta(minutes=45),
                           flight_duration=datetime.timedelta(minutes=29),
                           rtc=datetime.timedelta(minutes=35),
                           airline="A",
                           weight=10000)

    flights = {flight1, flight2, flight3, flight4, flight5}
    return {'slots': slots,
            'flights': flights}
