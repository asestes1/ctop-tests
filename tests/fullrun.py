# -*- coding: utf-8 -*-
"""
Created on Sun Jan 27 17:40:13 2019

@author: Alex
"""
import pandas
import os
import datetime
import scipy.stats as sps
import attr
import typing
import numpy.random  as npr
import collections

import context
import bctop.allocations


def flights_to_pd(flights: typing.Set[bctop.allocations.Flight]):
    data_dict = {f.fid: flight_to_dict(f) for f in flights}
    return pandas.DataFrame.from_dict(data_dict, orient='index')


def flight_to_dict(flight: bctop.allocations.Flight):
    return {'fid': flight.fid,
            'airline': flight.airline,
            'deptime': flight.deptime,
            'flight_duration': flight.flight_duration.total_seconds(),
            'rtc': flight.rtc.total_seconds(),
            'weight': flight.weight,
            'ota': flight.ota()
            }


def normalize_weights(flights: typing.Set[bctop.allocations.Flight]) -> typing.Set[bctop.allocations.Flight]:
    flights_by_airline = collections.defaultdict(set)
    for f in flights:
        flights_by_airline[f.airline].add(f)

    normalized_flights = set()
    for airline, airline_flights in flights_by_airline.items():
        avg_weight = sum(f.weight for f in airline_flights) / len(airline_flights)
        for f in airline_flights:
            normalized_flights.add(f.reweight(f.weight / avg_weight))
    return normalized_flights


def read_flights(filename: str, basetime: datetime.datetime,
                 rtc_dist: sps.rv_continuous,
                 weight_dist: sps.rv_continuous):
    test_data = pandas.read_excel(io=filename, index_row=None)
    flights = set()
    for row in test_data.itertuples():
        fid = row.fid
        airline = row.Airline
        departtime = basetime + datetime.timedelta(minutes=row.DT)
        duration = datetime.timedelta(minutes=row.FCA) - datetime.timedelta(minutes=row.DT)
        rtc = datetime.timedelta(seconds=float(rtc_dist.rvs(size=1)))
        weight = float(weight_dist.rvs(size=1))
        flights.add(bctop.allocations.Flight(fid=fid,
                                             airline=airline,
                                             deptime=departtime,
                                             flight_duration=duration,
                                             rtc=rtc,
                                             weight=weight))
    return flights


def generate_slots(start: datetime.datetime, end: datetime.datetime, slots_perhour: int):
    sid = 0
    slots = set()
    next_slot = start
    while next_slot <= end:
        slots.add(bctop.allocations.Slot(sid="S" + str(sid),
                                         time=next_slot))
        next_slot += datetime.timedelta(seconds=3600 / slots_perhour)
        sid += 1

    return slots


@attr.s(frozen=True, kw_only=True)
class ConstantVal(object):
    value = attr.ib()

    def __call__(self, *args, **kwargs):
        return self.value


@attr.s(frozen=True, kw_only=True)
class SlotAttrGetter(object):
    attrname = attr.ib(type=str)

    def __call__(self, slot: bctop.allocations.Slot, _):
        return getattr(slot, self.attrname)


@attr.s(frozen=True, kw_only=True)
class GroundDelayParser(object):
    weighted = attr.ib(type=bool)

    def __call__(self, slot: bctop.allocations.Slot, flight: bctop.allocations.Flight) -> float:
        if not self.weighted:
            weight = 1
        else:
            weight = flight.weight
        return weight * bctop.allocations.assigndelay(slot, flight).total_seconds()


@attr.s(frozen=True, kw_only=True)
class RrCostParser(object):
    weighted = attr.ib(type=bool)

    def __call__(self, flight: bctop.allocations.Flight) -> float:
        if not self.weighted:
            weight = 1
        else:
            weight = flight.weight
        return weight * flight.rtc.total_seconds()


def form_column(assignments, flights,
                assigned_getter: typing.Callable[[bctop.allocations.Slot, bctop.allocations.Flight], typing.Any],
                unassigned_getter: typing.Callable[[bctop.allocations.Flight], typing.Any]) -> pandas.Series:
    col = {}
    for f in flights:
        if f in assignments:
            col[f.fid] = assigned_getter(assignments[f], f)
        else:
            col[f.fid] = unassigned_getter(f)
    return pandas.Series(col)


if __name__ == '__main__':
    npr.seed(1)
    infilename = os.path.join(context.DATA_PATH, 'Scenario_W0.25BP2C60Q2D5.xlsx')
    myslots_perhour = 30
    rtc_dist_params = {'c': 0.2, 'loc': 0, 'scale': 60 * 90}
    weight_dist_params = {'c': 0.25, 'loc': 0, 'scale': 2}

    myrtc_dist = sps.triang(**rtc_dist_params)
    myweight_dist = sps.triang(**weight_dist_params)
    outfoldername = os.path.join(context.DATA_PATH, 'test_out_4')
    airline_cheats = True
    postswap=True
    with open(os.path.join(outfoldername, 'param_record.txt'), 'w') as paramfile:
        paramfile.write("RTC Distribution: Triangular, " + str(rtc_dist_params) + "\n")
        paramfile.write("RTC Distribution: Weight, " + str(weight_dist_params) + "\n")
        paramfile.write("Slots per hour: " + str(myslots_perhour) + "\n")
        paramfile.write("Airline Cheats: " + str(airline_cheats) + "\n")
        paramfile.write("Postswap: " + str(postswap) + "\n")

        paramfile.write("Seed: "+str(1))

    mybasetime = datetime.datetime(year=1970, month=1, day=1, hour=0, minute=0, second=0)
    methods = {'RBS': bctop.allocations.rbs,
               'CTOP': bctop.allocations.CtopRunner(cost_method=bctop.allocations.cost_rtc,
                                                    slotfiller=bctop.allocations.SlotFiller(compress=False),
                                                    airline_cheats=airline_cheats,
                                                    airline_cost_method=bctop.allocations.CostAssign(weighted=True),
                                                    ),
               'CMPR_RTC': bctop.allocations.CtopRunner(cost_method=bctop.allocations.cost_rtc,
                                                        slotfiller=bctop.allocations.SlotFiller(compress=True),
                                                        airline_cheats=airline_cheats,
                                                        airline_cost_method=bctop.allocations.CostAssign(weighted=True)
                                                        ),
               'CMPR_ONESTEP': bctop.allocations.CtopRunner(slotfiller=bctop.allocations.SlotFiller(compress=True),
                                                            cost_method=bctop.allocations.CostCompr(weighted=False),
                                                            airline_cheats=airline_cheats,
                                                            airline_cost_method=bctop.allocations.CostAssign(
                                                                weighted=True)
                                                            ),
               'CMPR_W_ONESTEP': bctop.allocations.CtopRunner(slotfiller=bctop.allocations.SlotFiller(compress=True),
                                                              cost_method=bctop.allocations.CostCompr(weighted=True),
                                                              airline_cheats=airline_cheats,
                                                              airline_cost_method=bctop.allocations.CostAssign(
                                                                  weighted=True)
                                                              ),
               'CMPR_ASSIGN': bctop.allocations.CtopRunner(slotfiller=bctop.allocations.SlotFiller(compress=True),
                                                           cost_method=bctop.allocations.CostAssign(weighted=False),
                                                           airline_cheats=airline_cheats,
                                                           airline_cost_method=bctop.allocations.CostAssign(
                                                               weighted=True)
                                                           ),
               'CMPR_WASSIGN': bctop.allocations.CtopRunner(slotfiller=bctop.allocations.SlotFiller(compress=True),
                                                            cost_method=bctop.allocations.CostAssign(weighted=True),
                                                            airline_cheats=airline_cheats,
                                                            airline_cost_method=bctop.allocations.CostAssign(
                                                                weighted=True)
                                                            ),

               'SYSOPT': bctop.allocations.SysOpt(weighted=False),
               'WSYSOPT': bctop.allocations.SysOpt(weighted=True)
               }

    num_trials: int = 100

    for i in range(0, num_trials):
        print(i)
        myflights = normalize_weights(read_flights(filename=infilename, basetime=mybasetime,
                                                   rtc_dist=myrtc_dist,
                                                   weight_dist=myweight_dist))
        outframe = flights_to_pd(myflights)
        myslots = generate_slots(start=mybasetime + datetime.timedelta(seconds=60 * 60 * 16),
                                 end=mybasetime + datetime.timedelta(seconds=60 * 60 * 36),
                                 slots_perhour=30)
        for name, m in methods.items():
            assignment = m(flights=myflights, slots=myslots)
            if(postswap):
                assignment = bctop.allocations.apply_swaps(flights=myflights, assignments=assignment)

            slot_id_col = form_column(assignment, myflights, SlotAttrGetter(attrname='sid'), ConstantVal(value='NONE'))
            slot_time_col = form_column(assignment, myflights, SlotAttrGetter(attrname='time'),
                                        ConstantVal(value='NONE'))
            gd_col = form_column(assignment, myflights, assigned_getter=GroundDelayParser(weighted=False),
                                 unassigned_getter=ConstantVal(value=0))
            rr_col = form_column(assignment, myflights,
                                 assigned_getter=ConstantVal(value=0),
                                 unassigned_getter=RrCostParser(weighted=False)
                                 )
            total_col = form_column(assignment, myflights, assigned_getter=GroundDelayParser(weighted=False),
                                    unassigned_getter=RrCostParser(weighted=False))
            wgd_col = form_column(assignment, myflights, assigned_getter=GroundDelayParser(weighted=True),
                                  unassigned_getter=ConstantVal(value=0))
            wrr_col = form_column(assignment, myflights,
                                  assigned_getter=ConstantVal(value=0),
                                  unassigned_getter=RrCostParser(weighted=True)
                                  )
            wtotal_col = form_column(assignment, myflights, assigned_getter=GroundDelayParser(weighted=True),
                                     unassigned_getter=RrCostParser(weighted=True))

            outframe['SLOTTIME_' + name] = slot_time_col
            outframe['SLOTID_' + name] = slot_id_col
            outframe['GD_' + name] = gd_col
            outframe['RRCOST_' + name] = rr_col
            outframe['TOTALGDE_' + name] = total_col
            outframe['WGD_' + name] = wgd_col
            outframe['WRRCOST_' + name] = wrr_col
            outframe['WTOTALGDE_' + name] = wtotal_col
            outframe.to_csv(os.path.join(outfoldername, 'trial' + str(i) + '.csv'), index=False)
