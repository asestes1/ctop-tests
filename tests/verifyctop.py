import operator
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import bctop.allocations
import tests.instance_def

instance = tests.instance_def.small_instance()
methods = {'RBS': bctop.allocations.rbs,
           'CTOP': bctop.allocations.CtopRunner(cost_method=bctop.allocations.cost_rtc,
                                                slotfiller=bctop.allocations.SlotFiller(compress=False)),
           'CMPR_RTC': bctop.allocations.CtopRunner(cost_method=bctop.allocations.cost_rtc,
                                                    slotfiller=bctop.allocations.SlotFiller(compress=True)),
           'CMPR_ONESTEP': bctop.allocations.CtopRunner(slotfiller=bctop.allocations.SlotFiller(compress=True),
                                                        cost_method=bctop.allocations.CostCompr(weighted=False)),
           'CMPR_W_ONESTEP': bctop.allocations.CtopRunner(slotfiller=bctop.allocations.SlotFiller(compress=True),
                                                          cost_method=bctop.allocations.CostCompr(weighted=True)),
           'CMPR_ASSIGN': bctop.allocations.CtopRunner(slotfiller=bctop.allocations.SlotFiller(compress=True),
                                                       cost_method=bctop.allocations.CostAssign(weighted=False)),
           'CMPR_WASSIGN': bctop.allocations.CtopRunner(slotfiller=bctop.allocations.SlotFiller(compress=True),
                                                        cost_method=bctop.allocations.CostAssign(weighted=True)),

           'SYSOPT': bctop.allocations.SysOpt(weighted=False),
           'WSYSOPT': bctop.allocations.SysOpt(weighted=True)
           }

for name, m in methods.items():
    print(name)
    allocation = m(**tests.instance_def.small_instance())
    for f in sorted(instance['flights'], key=operator.attrgetter('fid')):
        if f in allocation:
            print(f.fid, allocation[f])
        else:
            print(f.fid, "rerouted")