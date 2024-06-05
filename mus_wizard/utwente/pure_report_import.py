import csv
from collections import defaultdict
from datetime import datetime
from zipfile import BadZipFile

import aiometer
import motor.motor_asyncio
import openpyxl_dictreader
import termcharts
from rich import console, layout, panel, print, table

from mus_wizard.constants import MONGOURL


class PureReport():
    def __init__(self, filenames: list[str] = None):
        self.mongoclient: motor.motor_asyncio.AsyncIOMotorClient = motor.motor_asyncio.AsyncIOMotorClient(
            MONGOURL).metadata_unification_system
        self.filenames: list[str] = filenames
        self.library_employees = ['M7731800',
                                  'M7642439'
                                  'M7642471',
                                  'M7641474',
                                  'M7640169',
                                  ]
        self.namemapping = {'M7731800': 'Schipper, Liene (UT-LISA) [library] [library]',
                            'M7642471': 'Bevers, René (UT-LISA) [library] [library]',
                            'M7641474': 'Leusink-Eikelboom, Yvonne (UT-LISA) [library] [library]',
                            'M7640169': 'Bakker-Koorman, Karin (UT-LISA) [library] [library]',
                            'M7642439': 'Exterkate-ten Heggeler, Yvonne (UT-LISA) [library] [library]',
                            'M7692738': 'Scholten-Koop, Bertine (UT-EEMCS) [secretary] [SCS]',
                            'M7693261': 'Steenbergen-Boeringa, Marion (UT-EEMCS) [secretary] [FMT]',
                            'M7640406': 'Broersma, Hajo (UT-EEMCS) [researcher] [FMT]',
                            'M7668993': 'Lopuhaä-Zwakenberg, Milan (UT-EEMCS) [researcher] [FMT]',
                            'M7660017': 'Meuwly, Didier (UT-EEMCS) [researcher] [DMB]',
                            'M7688543': 'Huisman, Marieke (UT-EEMCS) [researcher] [FMT]',
                            'M7687683': 'Jonker, Mattijs (UT-EEMCS) [researcher] [DACS]',
                            'M7662106': 'Bukhsh, Faiza (UT-EEMCS) [researcher] [DMB]',
                            'M7712831': 'Prince Sales, Tiago (UT-EEMCS) [researcher] [SCS]',
                            'M7667645': 'Wang, Shenghui (UT-EEMCS) [researcher] [HMI]',
                            'M7715214': 'Miranda Soares, Filipi (UT-EEMCS) [researcher] [SCS]',
                            'M7680523': 'Stoelinga, Mariëlle (UT-EEMCS) [researcher] [FMT]',
                            'M7660096': 'Kamminga, Jacob (UT-EEMCS) [researcher] [PS]',
                            'M7663975': 'Müller, Moritz (UT-EEMCS) [researcher] [DACS]',
                            'M7646927': 'Theune, Mariet (UT-EEMCS) [researcher] [HMI]',
                            'M7716307': 'Varenhorst, Ivo (UT-EEMCS) [researcher] [CAES]',
                            'M7666116': 'Bemthuis, Rob (UT-EEMCS) [researcher] [PS]',
                            'M7700606': 'Chen, Kuan (UT-EEMCS) [researcher] [CAES]',
                            'M7695442': 'Le Viet Duc, Duc (UT-EEMCS) [researcher] [PS]',
                            'M7668390': 'Atashgahi, Zahra (UT-EEMCS) [researcher] [DMB]',
                            'M7664330': 'Seifert, Christin (UT-EEMCS) [researcher] [DMB]',
                            'M7700813': 'Rook, Jeroen (UT-EEMCS) [researcher] [DMB]',
                            'M7717102': 'Khadka, Shyam Krishna (UT-EEMCS) [researcher] [DACS]',
                            'M7642982': 'Rijswijk-Deij, Roland van (UT-EEMCS) [researcher] [DACS]',
                            'M7700625': 'Nguyen, Minh Son (UT-EEMCS) [researcher] [PS]',
                            'M7664572': 'Ham-de Vos, Jeroen van der (UT-EEMCS) [researcher] [DACS]',
                            'M7668017': 'Sarmah, Dipti (UT-EEMCS) [researcher] [SCS]',
                            'M7647139': 'Veldhuis, Raymond (UT-EEMCS) [researcher] [DMB]',
                            'M7704167': 'Gillani, Ghayoor (UT-EEMCS) [researcher] [CAES]',
                            'M7668807': 'Haq, Yasir (UT-BMS) [researcher] [IEBIS]',
                            'M7669053': 'Rangel Carneiro Magalhaes, Syllas (UT-EEMCS) [researcher] [DACS]',
                            'M7700537': 'Talavera Martínez, Estefanía (UT-EEMCS) [researcher] [DMB]'
                            }

    def run(self):
        # self.mongoclient.get_io_loop().run_until_complete(self.load_reports())
        self.mongoclient.get_io_loop().run_until_complete(self.process_data())

    async def load_reports(self):
        async def load_report(filename):
            data = []
            with open(filename, 'r', encoding='utf-8') as file:
                if filename.endswith('.xlsx'):
                    try:
                        reader = openpyxl_dictreader.DictReader(file, 'Sheet1')
                    except BadZipFile:
                        reader = openpyxl_dictreader.DictReader(file, 'Sheet0')
                elif filename.endswith('.csv'):
                    reader = csv.DictReader(file, delimiter=',')
                for row in reader:
                    for key, value in row.items():
                        if '|' in value:
                            row[key] = [i.strip() for i in value.split('|')]
                    data.append(row)
            return [filename, data]

        self.results = defaultdict()
        async with aiometer.amap(load_report, self.filenames, max_at_once=5, max_per_second=5) as results:
            async for response in results:
                uploadresult = await self.mongoclient[response[0]].insert_many(response[1])
                print('retrieved data from', response[0])

    async def process_data(self):
        beforepilot = self.mongoclient['eemcs_pure_report_before_pilot_tcs.csv']
        duringpilot = self.mongoclient['eemcs_pure_report_midterm_pilot_23-04-2024.csv']
        oldpapers = []
        newpapers = []
        monthdatalist = []
        pureids = set()
        comparisonlist = []
        async for item in beforepilot.find():
            oldpapers.append(item)
            pureids.add(item['pureid'])
        async for item in duringpilot.find():
            created = datetime.strptime(item['date_created'][0:10], '%Y-%m-%d')
            if created < datetime(2024, 1, 1) and created > datetime(2022, 12, 31):
                comparisonlist.append(item)
            monthdatalist.append(created)
            if item['pureid'] not in pureids:
                if item['creator'] in self.library_employees:
                    item['pilot_paper'] = True
                else:
                    item['pilot_paper'] = False
                newpapers.append(item)

        monthmapping = {1 : 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Aug', 9: 'Sep',
                        10: 'Oct', 11: 'Nov', 12: 'Dec'}
        data_per_month = {2023: {}, 2024: {}}
        for year in range(2023, 2025):
            for month in range(1, 13):
                if year == 2024:
                    if month > 4:
                        data_per_month[year][monthmapping[month]] = 0
                data_per_month[year][monthmapping[month]] = sum(
                    [1 for x in monthdatalist if x.month == month and x.year == year])
        listnum = 0
        charts = []
        statstables = []
        titles = []
        idtables = []
        publishertables = []
        for paperset in [newpapers, comparisonlist]:
            listnum += 1
            ids = [x['creator'] for x in paperset]
            publishers = defaultdict(int)
            for paper in paperset:
                publishers[paper['publisher_journal']] += 1

            counts = defaultdict(int)
            pergroup = defaultdict(int)
            perrole = defaultdict(int)
            idlist = []
            for id in ids:
                counts[id] += 1
            try:
                for id, count in counts.items():
                    idlist.append({'id'     : id,
                                   'name'   : self.namemapping[id].split('(')[0] if id in self.namemapping else '-',
                                   'faculty': self.namemapping[id].split('(UT-')[1].split(')')[
                                       0] if id in self.namemapping else '-',
                                   'group'  : self.namemapping[id].split('[')[2].split(']')[
                                       0] if id in self.namemapping else '-',
                                   'role'   : self.namemapping[id].split('[')[1].split(']')[
                                       0] if id in self.namemapping else '-',
                                   'count'  : count
                                   })
            except Exception as e:
                print(e)
                print(id, count)
                print(self.namemapping[id])

            idlist.sort(key=lambda x: x['count'], reverse=True)

            idtable = table.Table(title='Papers entered by ...', show_lines=True)
            idtable.add_column('id', justify='right', style='dim')
            idtable.add_column('name', justify='left', style='yellow', overflow='ellipsis')
            idtable.add_column('faculty', justify='left', style='dim')
            idtable.add_column('group', justify='left', style='dim')
            idtable.add_column('role', justify='left', style='green')
            idtable.add_column('# papers added', justify='right', style='cyan')

            publishertable = table.Table(title='Publishers', show_lines=True)
            publishertable.add_column('publisher', justify='left', style='yellow', overflow='ellipsis')
            publishertable.add_column('# papers', justify='right', style='cyan')
            for item in publishers.items():
                publishertable.add_row(*[str(i) for i in item])
            publishertables.append(publishertable)
            for item in idlist:
                idtable.add_row(*[str(i) for i in item.values()])
                perrole[item['role']] += 1
                pergroup[item['group']] += 1
            idtables.append(idtable)
            if listnum == 1:
                charts.append(termcharts.bar(data_per_month[2024], rich=True, mode='v'))
                days = datetime(2024, 4, 23) - datetime(2024, 3, 6)
                numpapers = len(paperset)
                papers_per_day = round(numpapers / days.days, 1)
                titles.append(f'TCS items added [cyan]during pilot[/cyan] (~{papers_per_day} per day)')
            elif listnum == 2:
                days = datetime(2023, 12, 31) - datetime(2023, 1, 1)
                numpapers = len(paperset)
                papers_per_day = round(numpapers / days.days, 1)
                charts.append(termcharts.bar(data_per_month[2023], rich=True, mode='v'))
                titles.append(f'TCS items added in [red]all of 2023[/red] (~{papers_per_day} per day)')

            nums = {}
            for item in [['Article'], ['Preprint'], ['Conference contribution', 'Conference article'],
                         ['Book', 'Chapter']]:
                nums[item[0]] = sum([1 for i in paperset if i['item_type'] in item])
            statstable = table.Table(show_lines=True)
            statstable.add_column('Added', justify='left', style='yellow')
            statstable.add_column('#', justify='center', style='green')
            statstable.add_column('%', justify='center', style='cyan')
            statstable.add_row('total', str(len(ids)), '-')
            statstable.add_row('by library backoffice',
                               str(sum([i['count'] for i in idlist if i['role'] == 'library'])), str(round(
                    sum([i['count'] for i in idlist if i['role'] == 'library']) * 100 / len(ids))) + '%')
            statstable.add_row('Item types', '#', '%', style='white')
            statstable.add_row('articles', str(nums['Article']), str(round(nums['Article'] * 100 / len(ids))) + '%')
            statstable.add_row('preprints', str(nums['Preprint']), str(round(nums['Preprint'] * 100 / len(ids))) + '%')
            statstable.add_row('conference papers', str(nums['Conference contribution']),
                               str(round(nums['Conference contribution'] * 100 / len(ids))) + '%')
            statstable.add_row('book (/chapters)', str(nums['Book']), str(round(nums['Book'] * 100 / len(ids))) + '%')
            statstables.append(statstable)

        lay = layout.Layout()
        lay.split_column(
            layout.Layout(name='tables'),
            layout.Layout(name='charts'),
        )
        lay['tables'].split_row(
            layout.Layout(name='table1'),
            layout.Layout(name='table2'),
        )
        lay['charts'].split_row(
            layout.Layout(name='chart1'),
            layout.Layout(name='chart2'),
        )

        lay['chart1'].update(panel.Panel(charts[0], title='papers/month [cyan]2024[/cyan]'))
        lay['chart2'].update(panel.Panel(charts[1], title='papers/month [red]2023[/red]', style='on grey27'))
        lay['table1'].update(panel.Panel(statstables[0], title=titles[0]))
        lay['table2'].update(panel.Panel(statstables[1], title=titles[1], style='on grey27'))
        cons = console.Console(record=True)

        cons.print(lay)
        from rich.terminal_theme import SVG_EXPORT_THEME

        cons.save_svg("example.svg", title="Pure pilot update", theme=SVG_EXPORT_THEME)
        '''
        cons.print(idtables[0])
        cons.print(idtables[1])

        cons.print(publishertables[0])
        cons.print(publishertables[1])
        '''
