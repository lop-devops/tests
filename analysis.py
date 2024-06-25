#!/usr/bin/env python3

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# Copyright: 2023 IBM
# Author: Misbah Anjum N <misanjum@linux.vnet.ibm.com>


'''
    analysis.py script is aimed to help in analysis/comparison of avocado test runs
    by generating a simple excel file (.xlsx). The results.json file which gets created
    after avocado run is passed as input in command line while running this script and
    depending on the flag/options provided, the excel analysis/omparison sheet will be
    generated.

    Prerequsites:-
    pip3 install pandas[excel]
    (or)
    dnf install python3-pandas python3-numpy python3-openpyxl

    flags/options:-
    1. --new-analysis
    2. --add-to-existing
    3. --compare-two-results

    python3 analysis.py --new-analysis <json_file>
    python3 analysis.py --add-to-existing <xlsx_file> <json_file>
    python3 analysis.py --compare-two-results <old_json_file> <new_json_file>

    Check README.md for more explanation
'''


import sys
import json
import pandas as pd
from openpyxl.styles import Font, Border, Side, PatternFill, Alignment


def test_analysis(data):
    '''
        This function is used to generate an excel file which contains a summary of
        avaocado based test runs. It reads results.json as input and generates a .xlsx
        file as output.
    '''

    # Extract job name from debuglog attribute
    job_name = data['debuglog'].split('/')[-2]

    # Create a DataFrame
    dataframe = pd.DataFrame(columns=['Name', 'Status', 'Fail Reason'])

    # Add rows for job name and other attributes
    dataframe.loc[0] = ['', 'Job Name', job_name]
    dataframe.loc[1] = ['', 'Fail', data['failures']]
    dataframe.loc[2] = ['', 'Error', data['errors']]
    dataframe.loc[3] = ['', 'Skip', data['skip']]
    dataframe.loc[4] = ['', 'Interrupt', data['interrupt']]
    dataframe.loc[5] = ['', 'Cancel', data['cancel']]
    dataframe.loc[6] = ['', 'Pass', data['pass']]
    dataframe.loc[7] = ['', 'White-Board', data['tests'][0]['whiteboard']]

    # Loop through the 'tests' list in the JSON data and add rows
    for i, test in enumerate(data['tests']):
        dataframe.loc[i + 8] = [test['name'],
                                test['status'], test['fail_reason']]

    # Save the DataFrame to a Excel file
    dataframe.to_excel('Analysis.xlsx', index=False)


def comparison_analysis(excel, data):
    '''
        This function is used to generate an excel sheet which gives delta comparison
        of two test avocado based test runs. Using excel sheet produced from the
        function: test_analysis(data) and results.json as inputs, it generate a .xlsx
        file as output.
    '''

    # store test_names in existing excel file
    old_dataframe = pd.read_excel(excel)
    test_names = old_dataframe[old_dataframe.columns[0]]
    test_names = [test_names[x] for x in range(8, len(old_dataframe.index))]

    # Extract job name from debuglog attribute
    job_name = data['debuglog'].split('/')[-2]

    # Create a DataFrame
    new_dataframe = pd.DataFrame(columns=['Status', 'Fail Reason'])

    # Add rows for job name and other attributes
    new_dataframe.loc[0] = ['Job Name', job_name]
    new_dataframe.loc[1] = ['Fail', data['failures']]
    new_dataframe.loc[2] = ['Error', data['errors']]
    new_dataframe.loc[3] = ['Skip', data['skip']]
    new_dataframe.loc[4] = ['Interrupt', data['interrupt']]
    new_dataframe.loc[5] = ['Cancel', data['cancel']]
    new_dataframe.loc[6] = ['Pass', data['pass']]
    new_dataframe.loc[7] = ['White-Board', data['tests'][0]['whiteboard']]

    # Loop through the 'tests' list in the JSON data and add rows
    for i, test in enumerate(data['tests']):
        found = 0
        for j in range(len(test_names)):
            if test['name'] == test_names[j]:
                new_dataframe.loc[j + 8] = [test['status'],
                                            test['fail_reason']]
                found = 1
                break
        if found == 0:
            new = [test['name']]
            for i in range(len(old_dataframe.columns)-1):
                new.append("")
            old_dataframe.loc[len(old_dataframe.index)] = new
            new_dataframe.loc[len(old_dataframe.index) -
                              1] = [test['status'], test['fail_reason']]

    final_res = pd.concat([old_dataframe, new_dataframe], axis=1)
    final_res.to_excel(excel, index=False)

    # Add the Result column to compare two results
    if "--compare-two-results" in sys.argv:
        dataframe = pd.read_excel(excel)
        results = []
        for i in range(len(dataframe.index)):
            if dataframe.loc[i].iat[-2] == dataframe.loc[i].iat[-4]:
                results.append("")
            else:
                if dataframe.loc[i].iat[-4] == "PASS" and not pd.isnull(dataframe.loc[i].iat[-2]):
                    results.append("REGRESSION")
                elif dataframe.loc[i].iat[-2] == "PASS" and not pd.isnull(dataframe.loc[i].iat[-4]):
                    results.append("SOLVED")
                elif pd.isnull(dataframe.loc[i].iat[-4]) or pd.isnull(dataframe.loc[i].iat[-2]):
                    results.append("")
                else:
                    results.append("DIFF")

        result_dataframe = pd.DataFrame(columns=['Result'])
        for i in range(8, len(results)):
            result_dataframe.loc[i] = results[i]

        final_dataframe = pd.concat([dataframe, result_dataframe], axis=1)
        final_dataframe.to_excel(excel, index=False)


def deco(excel):
    '''
        This function is used to conditionally format the xlsx file
        Libraries used: ExcelWriter, openpyxl
    '''

    # Create a sample DataFrame
    dataframe = pd.read_excel(excel)

    # Create a Pandas ExcelWriter object and write to Excel file
    excel_writer = pd.ExcelWriter(excel, engine='openpyxl')
    dataframe.to_excel(excel_writer, sheet_name='Sheet1', index=False)

    # Access the workbook and worksheet objects
    workbook = excel_writer.book
    worksheet = excel_writer.sheets['Sheet1']

    # Column Width
    worksheet.column_dimensions['A'].width = 60
    worksheet.column_dimensions['B'].width = 20
    worksheet.column_dimensions['C'].width = 80
    worksheet.column_dimensions['D'].width = 20
    worksheet.column_dimensions['E'].width = 80
    worksheet.column_dimensions['F'].width = 20

    # Apply styles to the entire sheet
    for row in worksheet.iter_rows(min_row=2, max_row=len(dataframe) + 1):
        for cell in row:
            cell.font = Font(size=15)
            cell.border = Border(left=Side(border_style='thin', color='000000'),
                                 right=Side(border_style='thin',
                                            color='000000'),
                                 top=Side(border_style='thin', color='000000'),
                                 bottom=Side(border_style='thin', color='000000'))
            cell.alignment = Alignment(wrap_text=True, vertical='center')

    # Apply header formatting
    for cell in worksheet[1]:
        cell.font = Font(size=18, bold=True)  # White text color
        # Blue background color
        cell.fill = PatternFill(start_color='ADD8E6',
                                end_color='ADD8E6', fill_type='solid')

    # Conditional formatting for the "Result" column if present
    try:
        for idx, value in enumerate(dataframe['Result'], start=2):
            cell = worksheet.cell(row=idx, column=6)
            if value == 'DIFF':
                cell.fill = PatternFill(
                    start_color='FF0000', end_color='FF0000', fill_type='solid')  # Red
            elif value == 'SOLVED':
                cell.fill = PatternFill(
                    start_color='39E75F', end_color='39E75F', fill_type='solid')  # Green
            elif value == 'REGRESSION':
                cell.fill = PatternFill(
                    start_color='FFA500', end_color='FFA500', fill_type='solid')  # Orange
    except Exception as e:
        pass

    # Save the styled Excel file
    workbook.save(excel)


def main():
    try:
        if "--new-analysis" in sys.argv:
            with open(sys.argv[-1], 'r') as json_file:
                data = json.load(json_file)
            test_analysis(data)
            deco("Analysis.xlsx")

        elif "--add-to-existing" in sys.argv:
            with open(sys.argv[-1], 'r') as json_file:
                data = json.load(json_file)
            excel = sys.argv[-2]
            comparison_analysis(excel, data)
            deco(excel)

        elif "--compare-two-results" in sys.argv:
            with open(sys.argv[-2], 'r') as json_file:
                data = json.load(json_file)
            test_analysis(data)
            deco("Analysis.xlsx")

            with open(sys.argv[-1], 'r') as json_file:
                data = json.load(json_file)
            comparison_analysis("Analysis.xlsx", data)
            deco("Analysis.xlsx")

        else:
            raise Exception

    except Exception as e:
        print(str(e))
        print("\nPay attention on the usage:\n"+usage())
        sys.exit(1)


def usage():
    return ("python3 analysis.py --new-analysis <json_file>\n\
python3 analysis.py --add-to-existing <xlsx_file> <json_file>\n\
python3 analysis.py --compare-two-results <old_json_file> <new_json_file>\n")


if __name__ == '__main__':
    main()
