import pandas as pd
import streamlit as st
from pymongo import MongoClient
import os
from collections import Counter
from itertools import chain
from rich import print
import xlsxwriter
from datetime import datetime
from collections import defaultdict

MONGOURL = 'mongodb://smops:bazending@localhost:27017/'

st.set_page_config(page_title='UT Publish & Read overview',
                    page_icon=':books:',
                    layout='wide')
client = MongoClient(MONGOURL)
db = client.library_overview
last_saves = defaultdict(dict)
itemtypes = ['journal-article', 'book-chapter', 'book', 'conference-proceedings', 'other']
oa_types = ['gold', 'hybrid', 'bronze', 'green', 'closed']
default_parameters = {'years': [2020, 2024], 'itemtypes': ['journal-article'], 'oa_types':  ['gold', 'hybrid', 'bronze', 'green', 'closed']}
@st.cache_data(ttl=60*60*24*7)
def get_grouplist():
    db = client.library_overview
    item = db.data_export_rich.find_one()
    return list(item.keys())[16:]


@st.cache_data(ttl=60*60*24)
def get_publisherlist():
    collection_pub = client.library_overview.data_export_rich
    collection_ref = client.library_overview.data_export_refs
    pipeline = [
        {"$group": {"_id": "$publisher", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$project": {"publisher": "$_id", "count": 1, "_id": 0}}
    ]

    published = list(collection_pub.aggregate(pipeline))    
    refs = list(collection_ref.aggregate(pipeline))
    merged_results = [
    {"publisher": value, "count": count}
    for value, count in Counter(
        dict(chain(
            ((item['publisher'], item['count']) for item in published),
            ((item['publisher'], item['count']) for item in refs)
        ))
    ).items()
    ]
    return sorted(merged_results, key=lambda x: x['count'], reverse=True)

def normalize_list(lst):
    min_val = min(lst)
    max_val = max(lst)
    if max_val == min_val:
        return [1.0] * len(lst)  # If all values are the same, return a flat line
    return [round((x - min_val) / (max_val - min_val), 2) for x in lst]

@st.cache_data(ttl=60*60*24)
def get_stats(collectionname: str, selected_itemtypes = ['journal-article'], selected_faculty=None, selected_publisher=None, attribute='publisher'):
    print(f'[{datetime.now().strftime("%m-%d %H:%M:%S")}] getting stats for: {collectionname=}, {selected_faculty=}, {selected_publisher=}, {attribute=}')
    
    sheetname = f'{attribute}'
    if 'data_export_rich' in collectionname:
        sheetname = sheetname + ' (published)'
    else:
        sheetname = sheetname + ' (referenced)'
    
    years = range(2020,2025)
    itemtypes = ['journal-article', 'book-chapter', 'book', 'conference-proceedings', 'other']
    oa_types = ['gold', 'hybrid', 'bronze', 'green', 'closed']

    excel_columns = [attribute] 
    if attribute == 'journal':
        excel_columns.extend(['issns'])
    excel_columns.extend(['total_count', 'oa_count', 'oa_percentage'])
    for year in years:
        excel_columns.append(str(year))
    for oa_type in oa_types:
        excel_columns.append(f'oa_{oa_type}')
        for year in years:
            excel_columns.append(f'oa_{oa_type}_{year}')
    for itemtype in itemtypes:
        excel_columns.append(f'{itemtype}')
        for year in years:
            excel_columns.append(f'{itemtype}_{year}')
    excel_columns2 = [attribute, 'total_count', 'oa_count', 'oa_percentage']
    for year in years:
        excel_columns2.append(str(year))
    for oa_type in oa_types:
        excel_columns2.append(f'oa_{oa_type}')
        for year in years:
            excel_columns2.append(f'oa_{oa_type}_{year}')
    for itemtype in itemtypes:
        if itemtype == 'journal-article':
            excel_columns2.append(f'{itemtype}')
            for year in years:
                excel_columns2.append(f'{itemtype}_{year}')

    collection = db[collectionname]
    match_condition = {
        "type": {'$in':selected_itemtypes}
    }

    if selected_faculty:
        match_condition[selected_faculty] = True
    elif selected_publisher:
        match_condition["publisher"] = selected_publisher
        attribute = 'faculty'

    pipeline = [
        {"$match": match_condition},
        {"$project": {
            "year": 1,
            "is_oa": 1,
            "open_access_type": 1,
            "publisher": 1,
            "journal": 1,
            "type": 1,
            'issn': 1,
            "faculties": {
                "$setUnion": [
                    {"$cond": [{"$eq": ["$EEMCS", True]}, ["EEMCS"], []]},
                    {"$cond": [{"$eq": ["$TNW", True]}, ["TNW"], []]},
                    {"$cond": [{"$eq": ["$BMS", True]}, ["BMS"], []]},
                    {"$cond": [{"$eq": ["$ITC", True]}, ["ITC"], []]},
                    {"$cond": [{"$eq": ["$ET", True]}, ["ET"], []]}
                ]
            }
        }}
    ]

    if attribute == 'faculty':
        pipeline.extend([
            {"$unwind": "$faculties"},
            {"$group": {
                "_id": {
                    "faculty": "$faculties",
                    "year": "$year",
                    "is_oa": "$is_oa",
                    "open_access_type": "$open_access_type",
                    "type": "$type"
                },
                "count": {"$sum": 1}
            }}
        ])
    elif attribute == 'journal':
        pipeline.append({
            "$group": {
                "_id": {
                    f"{attribute}": f"${attribute}",
                    "issn": "$issn",
                    "year": "$year",
                    "is_oa": "$is_oa",
                    "open_access_type": "$open_access_type",
                    "type": "$type"
                },
                "count": {"$sum": 1}
            }}
    )
    else:
        pipeline.append(
            {"$group": {
                "_id": {
                    f"{attribute}": f"${attribute}",
                    "year": "$year",
                    "is_oa": "$is_oa",
                    "open_access_type": "$open_access_type",
                    "type": "$type"
                },
                "count": {"$sum": 1}
            }}
        )
    
    if attribute == 'journal':
        pipeline.extend([
        {"$group": {
            "_id": f"$_id.{attribute}",
            "total_count": {"$sum": "$count"},
            "oa_count": {"$sum": {"$cond": [{"$eq": ["$_id.is_oa", True]}, "$count", 0]}},
            "counts_by_year": {
                "$push": {
                    "year": "$_id.year",
                    "count": "$count"
                }
            },
            "oa_types": {
                "$push": {
                    "type": "$_id.open_access_type",
                    "count": "$count",
                    "year": "$_id.year",
                }
            },
            "types": {
                "$push": {
                    "type": "$_id.type",
                    "count": "$count",
                    "year": "$_id.year",
                }
            },
            "issns": {"$addToSet": "$_id.issn"}
        }},
        {"$project": {
            attribute: "$_id",
            "total_count": 1,
            "oa_count": 1,
            "counts_by_year": 1,
            "oa_types": 1,
            "types": 1,
            "issns": {
                "$cond": {
                    "if": {"$isArray": "$issns"},
                    "then": {"$setDifference": ["$issns", [None]]},  # Remove any null values
                    "else": {"$cond": [{"$eq": ["$issns", None]}, [], ["$issns"]]}  # Handle non-array cases
                }
            },            
            "_id": 0,
        }},
        {"$sort": {"total_count": -1}}
        ])
    else:
        pipeline.extend([
        {"$group": {
            "_id": "$_id.faculty" if attribute == 'faculty' else f"$_id.{attribute}",
            "total_count": {"$sum": "$count"},
            "oa_count": {"$sum": {"$cond": [{"$eq": ["$_id.is_oa", True]}, "$count", 0]}},
            "counts_by_year": {
                "$push": {
                    "year": "$_id.year",
                    "count": "$count"
                }
            },
            "oa_types": {
                "$push": {
                    "type": "$_id.open_access_type",
                    "count": "$count",
                    "year": "$_id.year",
                }
            },
            "types": {
                "$push": {
                    "type": "$_id.type",
                    "count": "$count",
                    "year": "$_id.year",
                }
            },
        }},
        {"$project": {
            attribute: "$_id",
            "total_count": 1,
            "oa_count": 1,
            "counts_by_year": 1,
            "oa_types": 1,
            "types": 1,
            "_id": 0,
        }},
        {"$sort": {"total_count": -1}}
        ])

    
    result = list(collection.aggregate(pipeline))
    if not result:
        print(f'No result for request: {attribute=}, {collectionname=}, {selected_faculty=}, {selected_publisher=}')
        return pd.DataFrame()
    raw_df = pd.DataFrame(result)
    if attribute == 'journal':
        raw_df['issns'] = raw_df['issns'].apply(lambda x: x[0] if len (x)>0 else x)
        raw_df['issns'] = raw_df['issns'].apply(lambda x: [i for i in x if i])
 
    df = raw_df.copy()
    # Create a column with counts for itemtypes, oa_types, and totals for each year and overall
    df = create_split_columns(df)
    df['oa_count'] = df[['oa_gold', 'oa_hybrid', 'oa_bronze', 'oa_green']].sum(axis=1)
    df['oa_percentage'] = (df['oa_count'] / df['total_count'] * 100).round(2)
    #export the data
    export_data(collectionname, df, excel_columns, excel_columns2, sheetname, selected_faculty=selected_faculty, selected_publisher=selected_publisher)
    #fix up the df for display
    df['counts_by_year'] = df.apply(lambda row: [row[str(year)] for year in range(2020, 2024)], axis=1)
    df['total_count'] = df['total_count'].astype(int)
    df['normalized_counts'] = df['counts_by_year'].apply(lambda x: normalize_list(x))
    
    df=df.dropna(subset=[attribute])
    df=df.dropna(subset=['total_count'])
    return df, raw_df

def create_split_columns(df: pd.DataFrame, years: list = None, oa_types: list = None, itemtypes: list = None):
        if not years:
            years = range(2020, 2025)
        if not oa_types:
            oa_types = ['gold', 'hybrid', 'bronze', 'green', 'closed']
        if not itemtypes:
            itemtypes = ['journal-article']

        for year in years:
            df[str(year)] = df['counts_by_year'].apply(
                lambda x: sum(item['count'] for item in x if item['year'] == year)
            )
        for oa_type in oa_types:
            # Total count for each OA type
            df[f'oa_{oa_type}'] = df['oa_types'].apply(
                lambda x: sum(item['count'] for item in x if item['type'] == oa_type)
            )
            
            # Count for each OA type per year
            for year in years:
                df[f'oa_{oa_type}_{year}'] = df['oa_types'].apply(
                    lambda x: sum(item['count'] for item in x if item['type'] == oa_type and item['year'] == year)
                )


        for itemtype in itemtypes:
            try:
                # Total count for each itemtype
                df[f'{itemtype}'] = df['types'].apply(
                    lambda x: sum(item['count'] for item in x if item['type'] == itemtype)
                )
            except KeyError:
                    print(f'No items of type {itemtype} in this df.')
            # Count for each itemtype per year
            for year in years:
                try:
                    df[f'{itemtype}_{year}'] = df['types'].apply(
                        lambda x: sum(item['count'] for item in x if item['type'] == itemtype and item['year'] == year)
                    )
                except KeyError:
                    print(f'No items of type {itemtype} in this df.')
        return df
def export_data(collectionname: str, df: pd.DataFrame, excel_columns: list, excel_columns2: list, sheetname: str, selected_faculty=None, selected_publisher=None):
        try:
            df[excel_columns].to_excel(writer, sheet_name=sheetname, index=False)
        except KeyError:
            df[excel_columns2].to_excel(writer, sheet_name=sheetname, index=False)
def select_data_for_table(df, raw_df, attribute, parameters=None):
    baselist = [attribute]
    if attribute == 'journal' and 'issns' in raw_df.columns:
        baselist.extend(['issns'])
    baselist.extend(['total_count', 'oa_count', 'oa_percentage', 'counts_by_year', 'normalized_counts', 'oa_gold', 'oa_hybrid', 'oa_bronze', 'oa_green', 'oa_closed'])
    if parameters == default_parameters or not parameters:
        return df[baselist]
    else:
        print(parameters)
        years:list[int] = parameters.get('years')
        print(years)
        df = create_split_columns(raw_df, years=years)
        df['total_count'] = df.apply(lambda row: sum(row[str(year)] for year in years), axis=1)
        if 2024 in years and len(years) > 1:
            years = list(years)
            years.remove(2024)

        df['counts_by_year'] = df.apply(lambda row: [row[str(year)] for year in years], axis=1)
        df['normalized_counts'] = df['counts_by_year'].apply(lambda x: normalize_list(x))
        df['oa_count'] = df[['oa_gold', 'oa_hybrid', 'oa_bronze', 'oa_green']].sum(axis=1)
        df['oa_percentage'] = (df['oa_count'] / df['total_count'] * 100).round(2)
        df=df.dropna(subset=[attribute])
        df=df.dropna(subset=['total_count'])

        return df[baselist]
                


grouptab, publishertab = st.tabs(['By faculty', 'By publisher'])
global writer
instructions = None

with grouptab:
    parameters = {'years': list(range(2020,2024)), 'itemtypes': ['journal-article'], 'oa_types':  ['gold', 'hybrid', 'bronze', 'green', 'closed']}
    group = st.selectbox('Select a faculty:', ['EEMCS', 'BMS', 'ET', 'ITC', 'TNW'])
    itemtypes = st.multiselect('Item type', ['journal-article', 'book-chapter', 'book', 'conference-proceedings', 'other'], default='journal-article')
    filepath = os.path.join(os.getcwd(), 'library_xlsx_output', f'{group}.xlsx')
    writer = pd.ExcelWriter(filepath, engine="xlsxwriter")   

    with st.spinner('Retrieving data & building the dataset...'):
        publishers_pub, pp_raw= get_stats(collectionname='data_export_rich', selected_faculty=group, selected_itemtypes=itemtypes, attribute='publisher')
        journals_pub, jp_raw = get_stats(collectionname='data_export_rich', selected_faculty=group, selected_itemtypes=itemtypes, attribute='journal')
        publishers_ref, pr_raw = get_stats(collectionname='data_export_refs', selected_faculty=group, selected_itemtypes=itemtypes, attribute='publisher')
        journals_ref, jr_raw = get_stats(collectionname='data_export_refs', selected_faculty=group, selected_itemtypes=itemtypes, attribute='journal')
    
    writer.close()
    if any([publishers_pub.empty, journals_pub.empty, publishers_ref.empty, journals_ref.empty]):
        st.toast(f'Unable to show data for {group}. Possible cause: No results for selected filters. Select different filters and try again.', icon='❌')
    else:
        st.toast(f'Data for {group} retrieved!', icon="✅")
    
        filepath = os.path.join(os.getcwd(), 'library_xlsx_output', f'{group}.xlsx')

        

        st.header(f'Top journals and publishers for {group}')
        with open(filepath, "rb") as f:
            st.download_button(
                type='primary',
                label=f"💾 Download 📊 data for {group}",
                data=f,
                file_name=f"{group}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        with st.sidebar:
            st.subheader('Show data for year(s):')
            years = st.select_slider('Years', options=[2020, 2021, 2022, 2023, 2024], value=[2020, 2024])
            
            if len(years) == 2:
                years = range(years[0], years[1] + 1)

            parameters['years'] = years
            print(parameters)

            with st.expander("Explanation of results", expanded=True):
                st.markdown('''Each **total_count** column shows the total amount of items for the selection for that publisher or journal.
The trend of this number over the years is visualized as two line charts: one using the absolute values, and one normalized to better see the trend.
The visualizations do not include the current year, as it's still ongoing.

All tables are interactive:  
- Click on column headers to **sort** by that column
- Change column width by moving the border lines
- Select multiple columns/rows and press ctrl-c to copy them
- Hover over the mini-graphs to see the values for each point
- Hover over the top right of the table to find a small menu to:
    - **Enlarge** the table
    - **Download** the table as a CSV (remember that you can also download the detailed data as an excel, see the button above)
    - **Search** the table for any text you want
    ''')
            

        

        st.subheader(f'For works published by {group}')
        col1, col2 = st.columns(2)

        with col1:
            dataframe = select_data_for_table(publishers_pub, pp_raw, attribute='publisher', parameters=parameters)
            st.dataframe(
                dataframe,
                column_config={
                    "publisher": st.column_config.TextColumn("Publisher"),
                    'total_count': st.column_config.NumberColumn("Total Count"),
                    "oa_count": st.column_config.NumberColumn("OA Count"),
                    "oa_percentage": st.column_config.NumberColumn("OA %", format="%.2f%%"),
                    "counts_by_year": st.column_config.AreaChartColumn(
                        "Count/year",
                        width="medium",
                        y_min=0,
                        y_max=int(publishers_pub['counts_by_year'].apply(max).max())
                    ),
                    "normalized_counts": st.column_config.AreaChartColumn(
                    "Normalized Trend",
                    width="medium",
                    y_min=0,
                    y_max=1
                    ),
                    "oa_gold": st.column_config.NumberColumn("Gold OA"),
                    "oa_hybrid": st.column_config.NumberColumn("Hybrid OA"),
                    "oa_bronze": st.column_config.NumberColumn("Bronze OA"),
                    "oa_green": st.column_config.NumberColumn("Green OA"),
                    "oa_closed": st.column_config.NumberColumn("Closed"),
                },
                hide_index=True
            )

        with col2:
            dataframe2 = select_data_for_table(journals_pub, jp_raw, attribute='journal', parameters=parameters)
            print(dataframe2['issns'].head())
            st.dataframe(
                dataframe2,
                
                column_config={
                    "journal": st.column_config.TextColumn("Journal"),
                    'issns': st.column_config.ListColumn("ISSNs"),
                    'total_count': st.column_config.NumberColumn("Total Count"),
                    "oa_count": st.column_config.NumberColumn("OA Count"),
                    "oa_percentage": st.column_config.NumberColumn("OA %", format="%.2f%%"),
                    "counts_by_year": st.column_config.AreaChartColumn(
                        "Count/year",
                        width="medium",
                        y_min=0,
                        y_max=int(journals_pub['counts_by_year'].apply(max).max())
                    ),
                    "normalized_counts": st.column_config.AreaChartColumn(
                    "Normalized Trend",
                    width="medium",
                    y_min=0,
                    y_max=1
                    ),
                    "oa_gold": st.column_config.NumberColumn("Gold OA"),
                    "oa_hybrid": st.column_config.NumberColumn("Hybrid OA"),
                    "oa_bronze": st.column_config.NumberColumn("Bronze OA"),
                    "oa_green": st.column_config.NumberColumn("Green OA"),
                    "oa_closed": st.column_config.NumberColumn("Closed"),
                },
                hide_index=True
            )    
        
        
        st.subheader(f'For works referenced by {group}')

        col1, col2 = st.columns(2)
        with col1:
            dataframe3 = select_data_for_table(publishers_ref, pr_raw, attribute='publisher', parameters=parameters)
            st.dataframe(
                dataframe3,
                column_config={
                    "publisher": st.column_config.TextColumn("Publisher"),
                    'total_count': st.column_config.NumberColumn("Total Count"),
                    "oa_count": st.column_config.NumberColumn("OA Count"),
                    "oa_percentage": st.column_config.NumberColumn("OA %", format="%.2f%%"),
                    "counts_by_year": st.column_config.AreaChartColumn(
                        "Count/year",
                        width="medium",
                        y_min=0,
                        y_max=int(publishers_ref['counts_by_year'].apply(max).max())
                    ),
                    "normalized_counts": st.column_config.AreaChartColumn(
                    "Normalized Trend",
                    width="medium",
                    y_min=0,
                    y_max=1
                    ),
                    "oa_gold": st.column_config.NumberColumn("Gold OA"),
                    "oa_hybrid": st.column_config.NumberColumn("Hybrid OA"),
                    "oa_bronze": st.column_config.NumberColumn("Bronze OA"),
                    "oa_green": st.column_config.NumberColumn("Green OA"),
                    "oa_closed": st.column_config.NumberColumn("Closed"),
                },
                hide_index=True
            )    
        with col2:
            dataframe4 = select_data_for_table(journals_ref, jr_raw, attribute='journal', parameters=parameters)
            st.dataframe(
                dataframe4,
                column_config={
                    "journal": st.column_config.TextColumn("Journal"),
                    'total_count': st.column_config.NumberColumn("Total Count"),
                    "oa_count": st.column_config.NumberColumn("OA Count"),
                    "oa_percentage": st.column_config.NumberColumn("OA %", format="%.2f%%"),
                    "counts_by_year": st.column_config.AreaChartColumn(
                        "Count/year",
                        width="medium",
                        y_min=0,
                        y_max=int(journals_ref['counts_by_year'].apply(max).max())
                    ),
                    "normalized_counts": st.column_config.AreaChartColumn(
                    "Normalized Trend",
                    width="medium",
                    y_min=0,
                    y_max=1
                    ),
                    "oa_gold": st.column_config.NumberColumn("Gold OA"),
                    "oa_hybrid": st.column_config.NumberColumn("Hybrid OA"),
                    "oa_bronze": st.column_config.NumberColumn("Bronze OA"),
                    "oa_green": st.column_config.NumberColumn("Green OA"),
                    "oa_closed": st.column_config.NumberColumn("Closed"),

                },
                hide_index=True
            )       
with publishertab:
    with st.form('Publisher Filter'):
        publishers=get_publisherlist()
        publisher = st.selectbox('Publisher', publishers)
        publisher = publisher['publisher']
        itemtype = st.multiselect('Item type', ['journal-article', 'book-chapter', 'book', 'conference-proceeding', 'other'], default='journal-article')

        submit = st.form_submit_button('Retrieve data!')

    if submit and publisher:
        filepath = os.path.join(os.getcwd(), 'library_xlsx_output', f'{publisher}.xlsx')
        writer = pd.ExcelWriter(filepath, engine="xlsxwriter")   

        with st.spinner('Retrieving data & creating Excel files...'):
            stats_pub = get_stats('data_export_rich', selected_publisher=publisher, item_type=itemtype, attribute='group')
            stats_ref = get_stats('data_export_refs', selected_publisher=publisher, item_type=itemtype, attribute='group')
        
        writer.close()
        st.toast(f'Data for {publisher} retrieved! Itemtypes included: {itemtype if itemtype else "All items"}', icon="✅")
        st.header(f'Faculty statistics for {publisher}')
        with open(filepath, "rb") as f:
            st.download_button(
                type='primary',
                label=f"💾 Download 📊 data for {publisher}",
                data=f,
                file_name=f"{publisher}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        st.markdown('''Each **total_count** column shows the total amount of items for the selection for that publisher or journal.
The trend of this number over the years is visualized as two line charts: one using the absolute values, and one normalized to better see the trend.
The visualizations do not include the current year, as it's still ongoing.

All tables are interactive:  
- Click on column headers to **sort** by that column
- Hover over the graphs to see the values for each point
- Hover over the top right of the table to find a small menu to:
    - **Enlarge** the table
    - **Download** the table as a CSV (remember that you can also download the detailed data as an excel, see the button above)
    - **Search** the table for any text you want
    ''')
        st.subheader(f'Works from each faculty published by {publisher}')
        st.dataframe(
            stats_pub,
            column_config={
                "group": st.column_config.TextColumn("Faculty"),
                "total_count": st.column_config.NumberColumn("Total Count"),
                "oa_count": st.column_config.NumberColumn("OA Count"),
                "oa_percentage": st.column_config.NumberColumn("OA %", format="%.2f%%"),
                "counts_by_year": st.column_config.AreaChartColumn(
                    "Count/year",
                    width="medium",
                    y_min=0,
                    y_max=int(stats_pub['counts_by_year'].apply(max).max())
                ),
                "normalized_counts": st.column_config.AreaChartColumn(
                    "Normalized Trend",
                    width="medium",
                    y_min=0,
                    y_max=1
                ),
                "oa_gold": st.column_config.NumberColumn("Gold OA"),
                "oa_hybrid": st.column_config.NumberColumn("Hybrid OA"),
                "oa_bronze": st.column_config.NumberColumn("Bronze OA"),
                "oa_green": st.column_config.NumberColumn("Green OA"),
                "oa_closed": st.column_config.NumberColumn("Closed"),

            },
            hide_index=True
        )

        st.subheader(f'Works from each faculty referencing items published by {publisher}')
        st.dataframe(
            stats_ref,
            column_config={
                "group": st.column_config.TextColumn("Faculty"),
                "total_count": st.column_config.NumberColumn("Total Count"),
                "oa_count": st.column_config.NumberColumn("OA Count"),
                "oa_percentage": st.column_config.NumberColumn("OA %", format="%.2f%%"),
                "counts_by_year": st.column_config.AreaChartColumn(
                    "Count/year",
                    width="medium",
                    y_min=0,
                    y_max=int(stats_ref['counts_by_year'].apply(max).max())
                ),
                "normalized_counts": st.column_config.AreaChartColumn(
                    "Normalized Trend",
                    width="medium",
                    y_min=0,
                    y_max=1
                ),
                "oa_gold": st.column_config.NumberColumn("Gold OA"),
                "oa_hybrid": st.column_config.NumberColumn("Hybrid OA"),
                "oa_bronze": st.column_config.NumberColumn("Bronze OA"),
                "oa_green": st.column_config.NumberColumn("Green OA"),
                "oa_closed": st.column_config.NumberColumn("Closed"),
            },
            hide_index=True
        )
