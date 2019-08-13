import attr
import datetime
import typing
import operator
import gurobipy as grb
import collections


@attr.s(frozen=True, kw_only=True)
class Slot(object):
    sid = attr.ib(type=str)
    time = attr.ib(type=datetime.datetime)


@attr.s(frozen=True, kw_only=True)
class Flight(object):
    fid = attr.ib(type=str)
    airline = attr.ib(type=str)
    deptime = attr.ib(type=datetime.datetime)
    flight_duration = attr.ib(type=datetime.timedelta)
    rtc = attr.ib(type=datetime.timedelta)
    weight = attr.ib(type=float)

    def ota(self) -> datetime.timedelta:
        return self.deptime + self.flight_duration

    def reweight(self, weight: float):
        return Flight(fid=self.fid,
                      airline=self.airline,
                      deptime=self.deptime,
                      flight_duration=self.flight_duration,
                      rtc=self.rtc,
                      weight=weight)


def isfeasible(slot: Slot, flight: Flight) -> bool:
    return slot.time >= flight.ota()


def assigndelay(slot: Slot, flight: Flight) -> datetime.timedelta:
    return slot.time - flight.ota()


def airline_delay(assignment: typing.Dict[Flight, Slot], airline: str,
                  use_weights: bool = False) -> datetime.timedelta:
    total_time = datetime.timedelta(seconds=0)
    for f, s in assignment.items():
        if use_weights:
            weight = f.weight
        else:
            weight = 1.0

        if airline is None:
            total_time += assigndelay(slot=s, flight=f) * weight
        elif f.airline == airline:
            total_time += assigndelay(slot=s, flight=f) * weight

    return total_time


def get_airlineslots(assignment: typing.Dict[Flight, Slot], airline: str):
    return {f: s for f, s in assignment.items() if f.airline == airline}


def cost_rtc(flight: Flight, slot: Slot, *_, **__):
    return flight.rtc - assigndelay(slot=slot, flight=flight)


@attr.s(frozen=True, kw_only=True)
class CostCompr(object):
    weighted = attr.ib(type=bool)

    def __call__(self, flight: Flight, slot: Slot, assignments: typing.Dict[Flight, Slot],
                 slotfiller: typing.Callable, **kwargs) -> datetime.timedelta:
        if self.weighted:
            weight = flight.weight
        else:
            weight = 1.0
        base_cost = airline_delay(assignment=assignments, airline=flight.airline, use_weights=self.weighted)

        open_slots = {assignments[flight]: flight.airline}
        assignment_copy = dict(assignments)
        del assignment_copy[flight]

        assignment_copy = slotfiller(open_slots, assignment_copy)
        rr_cost = flight.rtc * weight + airline_delay(assignment=assignment_copy,
                                                      airline=flight.airline,
                                                      use_weights=self.weighted)
        return rr_cost - base_cost


@attr.s(frozen=True, kw_only=True)
class CostAssign(object):
    weighted = attr.ib(type=bool)

    def __call__(self, flight: Flight, slot: Slot, flights: typing.Iterable[Flight],
                 assignments: typing.Dict[Flight, Slot],
                 slotfiller: typing.Callable) -> datetime.timedelta:

        if self.weighted:
            weight = flight.weight
        else:
            weight = 1.0
        airlineflights = {f for f in flights if f.airline == flight.airline}
        airlineslots = get_airlineslots(assignment=assignments, airline=flight.airline)
        base_objval = build_assignmodel(slots=airlineslots.values(), flights=airlineflights,
                                        weighted=self.weighted).getAttr("ObjVal")
        base_cost = datetime.timedelta(seconds=base_objval)

        open_slots = {assignments[flight]: flight.airline}
        assignment_copy = dict(assignments)
        del assignment_copy[flight]

        assignment_copy = slotfiller(open_slots, assignment_copy)
        rr_airlineslots = get_airlineslots(assignment_copy, airline=flight.airline)
        rr_objval = build_assignmodel(slots=rr_airlineslots.values(), flights=airlineflights,
                                      weighted=self.weighted).getAttr("ObjVal")
        rr_cost = datetime.timedelta(seconds=rr_objval)
        return rr_cost - base_cost


class SlotTimeGetter(object):
    assignments: typing.Dict[Flight, Slot]

    def __init__(self, assignments):
        self.assignments = dict(assignments)

    def __call__(self, flight: Flight):
        return self.assignments[flight].time


@attr.s(kw_only=True, frozen=True)
class SlotFiller(object):
    compress = attr.ib(type=bool)

    def __call__(self, open_slots: typing.Dict[Slot, str], assignments: typing.Dict[Flight, Slot]) -> typing.Dict[
        Flight, Slot]:
        assignments = dict(assignments)
        open_slots = dict(open_slots)

        while open_slots:
            next_slot = min(open_slots.keys(), key=operator.attrgetter('time'))
            airline = open_slots[next_slot]
            del open_slots[next_slot]

            feasible_flights = {f for f, slot in assignments.items() if
                                f.ota() <= next_slot.time < slot.time}
            airline_flights = {f for f in feasible_flights if f.airline == airline}

            best_flight = False
            if self.compress and airline_flights:
                best_flight = min(airline_flights, key=SlotTimeGetter(assignments))
            elif feasible_flights:
                best_flight = min(feasible_flights, key=SlotTimeGetter(assignments))

            if best_flight:
                prev_slot = assignments[best_flight]
                del assignments[best_flight]
                assignments[best_flight] = next_slot
                open_slots[prev_slot] = airline

        return assignments


@attr.s(frozen=True, kw_only=True)
class CtopRunner(object):
    cost_method = attr.ib(type=typing.Callable[[Flight, Slot, typing.Dict[Flight, Slot]], datetime.timedelta])
    slotfiller = attr.ib(
        type=typing.Callable[[typing.Dict[Slot, str], typing.Dict[Flight, Slot]], typing.Dict[Flight, Slot]])
    airline_cheats = attr.ib(type=bool, default=False)
    airline_cost_method = attr.ib(type=typing.Callable[[Flight, Slot, typing.Dict[Flight, Slot]], datetime.timedelta],
                                  default=None)

    def __call__(self, slots: typing.Collection[Slot],
                 flights: typing.Collection[Flight]) -> typing.Dict[Flight, Slot]:
        assignments = rbs(slots, flights)
        unassigned_flights = set(flights)
        while unassigned_flights:
            flight = min(unassigned_flights, key=SlotTimeGetter(assignments))
            slot = assignments[flight]
            cost_diff = self.cost_method(flight=flight, slot=slot, flights=flights,
                                         assignments=assignments, slotfiller=self.slotfiller)

            airline_compat = True
            if self.airline_cheats:
                airline_cost_diff = self.airline_cost_method(flight=flight, slot=slot, flights=flights,
                                                             assignments=assignments, slotfiller=self.slotfiller)
                if airline_cost_diff > datetime.timedelta(seconds=0):
                    airline_compat = False

            if cost_diff <= datetime.timedelta(seconds=0) and airline_compat:
                open_slots = {slot: flight.airline}
                del assignments[flight]
                assignments = self.slotfiller(open_slots, assignments)

            unassigned_flights.remove(flight)

        return assignments


def rbs(slots: typing.Collection[Slot],
        flights: typing.Collection[Flight]) -> typing.Dict[Flight, Slot]:
    assignments = {}
    sorted_flights = sorted(set(flights), key=operator.methodcaller('ota'))
    remaining_slots = set(slots)

    for flight in sorted_flights:
        feasible_slots = {s for s in remaining_slots if isfeasible(s, flight)}
        if not feasible_slots:
            raise ValueError("Infeasible allocation; not enough slots")
        bestslot = min(feasible_slots, key=operator.attrgetter('time'))
        assignments[flight] = bestslot
        remaining_slots.remove(bestslot)
    return assignments


def assignvarname(slot: Slot, flight: Flight):
    return "S: " + str(slot.sid) + ", F: " + str(flight.fid)


def rrvarname(flight: Flight):
    return "F: " + str(flight.fid)


def build_assignmodel(slots: typing.Iterable[Slot], flights: typing.Iterable[Flight],
                      weighted: bool = False, verbose: bool = False) -> grb.Model:
    model = grb.Model()
    if not verbose:
        model.setParam("OutputFlag", 0)

    assign_vars: typing.Dict[typing.Tuple[Flight, Slot], grb.Var] = {}
    rr_vars: typing.Dict[Flight, grb.Var] = {}
    for f in flights:
        if not weighted:
            weight = 1.0
        else:
            weight = f.weight

        for s in slots:
            if isfeasible(slot=s, flight=f):
                assign_vars[f, s] = model.addVar(lb=0.0, ub=1.0,
                                                 obj=weight * assigndelay(slot=s, flight=f).total_seconds(),
                                                 vtype=grb.GRB.BINARY, name=assignvarname(slot=s, flight=f))
        rr_vars[f] = model.addVar(lb=0.0, ub=1.0, obj=weight * f.rtc.total_seconds(), vtype=grb.GRB.BINARY,
                                  name=rrvarname(flight=f))

    for f in flights:
        lhs = grb.LinExpr()
        lhs.add(rr_vars[f], 1.0)
        for s in slots:
            if isfeasible(slot=s, flight=f):
                lhs.add(assign_vars[f, s], 1.0)
        model.addConstr(lhs=lhs, sense=grb.GRB.EQUAL, rhs=1.0)

    for s in slots:
        lhs = grb.LinExpr()
        for f in flights:
            if isfeasible(slot=s, flight=f):
                lhs.add(assign_vars[f, s], 1.0)
        model.addConstr(lhs=lhs, sense=grb.GRB.LESS_EQUAL, rhs=1.0)

    model.optimize()
    return model


def read_assignment(slots: typing.Collection[Slot], flights: typing.Collection[Flight], model: grb.Model):
    assignments = {}
    for f in flights:
        for s in slots:
            if isfeasible(slot=s, flight=f):
                var = model.getVarByName(assignvarname(slot=s, flight=f))
                if abs(var.getAttr("X") - 1.0) < 0.001:
                    assignments[f] = s
    return assignments


@attr.s(frozen=True, kw_only=True)
class SysOpt(object):
    weighted = attr.ib(type=bool)

    def __call__(self, slots: typing.Collection[Slot], flights: typing.Collection[Flight]) -> typing.Dict[Flight, Slot]:
        grb_model = build_assignmodel(weighted=self.weighted, slots=slots, flights=flights)
        return read_assignment(model=grb_model, slots=slots, flights=flights)


def apply_swaps(flights: typing.Collection[Flight],
                assignments: typing.Dict[Flight, Slot]):
    airlineflightdict = collections.defaultdict(set)
    for f in flights:
        airlineflightdict[f.airline].add(f)

    airlineslotdict = collections.defaultdict(set)
    for f,slot in assignments.items():
        airlineslotdict[f.airline].add(slot)

    newassignment = {}
    for airline, f in airlineflightdict.items():
        airlineslots = airlineslotdict[airline]
        model = build_assignmodel(weighted=True, slots=airlineslots, flights=f)
        newassignment.update(read_assignment(model=model, slots=airlineslots, flights=f))
    return newassignment


# def ctop(slots: typing.Collection[Slot],
#          flights: typing.Collection[Flight]) -> typing.Dict[Flight, Slot]:
#     assignments = {}
#     sorted_flights = sorted(list(flights), key=operator.methodcaller('ota'))
#     remaining_slots = set(slots)
#     for flight in sorted_flights:
#         bestslot = min({s for s in remaining_slots if isfeasible(s, flight)}, key=operator.attrgetter('time'))
#         if assigndelay(bestslot, flight) < flight.rtc:
#             assignments[flight] = bestslot
#             remaining_slots.remove(bestslot)
#     return assignments
