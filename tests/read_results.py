import context
import os
import pandas

test_folder = os.path.join(context.DATA_PATH, "test_out_4")
method_names = ['RBS', 'CTOP', 'CMPR_RTC', 'CMPR_ONESTEP', 'CMPR_W_ONESTEP', 'CMPR_ASSIGN', 'CMPR_WASSIGN',
                'SYSOPT', 'WSYSOPT']
col_names = ['GD', 'RRCOST', 'TOTALGDE', 'WGD', 'WRRCOST', 'WTOTALGDE']
n_trials = 100

table_dict = {}
for m in method_names:
    row_dict = {}
    for c in col_names:
        avg = 0.0
        data_col = c + '_' + m
        for i in range(0, n_trials):
            filename = os.path.join(test_folder, "trial" + str(i) + ".csv")
            results = pandas.read_csv(filename)
            avg += results[data_col].mean() / n_trials
        row_dict[c] = avg
    table_dict[m] = row_dict

myframe = pandas.DataFrame.from_dict(table_dict,orient='index')
myframe.to_csv(os.path.join(test_folder, "summary.csv"))
