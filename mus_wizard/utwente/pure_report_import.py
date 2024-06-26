import csv
from collections import defaultdict
from datetime import datetime
from zipfile import BadZipFile

import aiometer
import motor.motor_asyncio
import openpyxl_dictreader
import termcharts
from rich import console, layout, panel, print, table, box
from rich.style import Style
from rich.segment import Segment
from rich.color import Color
from mus_wizard.constants import MONGOURL


class PureReport():
    def __init__(self, filenames: list[str] = None):
        self.mongoclient: motor.motor_asyncio.AsyncIOMotorClient = motor.motor_asyncio.AsyncIOMotorClient(
            MONGOURL).metadata_unification_system
        self.filenames: list[str] = ['eemcs_pure_report_before_pilot_tcs.csv',
                                     'eemcs_pure_report_midterm_pilot_23-04-2024.csv',
                                     'eemcs_pure_report_final_pilot_26-06-2024.csv']
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
                            'M7692738': 'Scholten-Koop, Bertine (UT-EEMCS) [secretary] [TCS]',
                            'M7693261': 'Steenbergen-Boeringa, Marion (UT-EEMCS) [secretary] [TCS]',
                            'M7640406': 'Broersma, Hajo (UT-EEMCS) [researcher] [TCS]',
                            'M7668993': 'Lopuhaä-Zwakenberg, Milan (UT-EEMCS) [researcher] [TCS]',
                            'M7660017': 'Meuwly, Didier (UT-EEMCS) [researcher] [TCS]',
                            'M7688543': 'Huisman, Marieke (UT-EEMCS) [researcher] [TCS]',
                            'M7687683': 'Jonker, Mattijs (UT-EEMCS) [researcher] [TCS/EE]',
                            'M7662106': 'Bukhsh, Faiza (UT-EEMCS) [researcher] [TCS]',
                            'M7712831': 'Prince Sales, Tiago (UT-EEMCS) [researcher] [TCS]',
                            'M7667645': 'Wang, Shenghui (UT-EEMCS) [researcher] [TCS]',
                            'M7715214': 'Miranda Soares, Filipi (UT-EEMCS) [researcher] [TCS]',
                            'M7680523': 'Stoelinga, Mariëlle (UT-EEMCS) [researcher] [TCS]',
                            'M7660096': 'Kamminga, Jacob (UT-EEMCS) [researcher] [TCS]',
                            'M7663975': 'Müller, Moritz (UT-EEMCS) [researcher] [TCS/EE]',
                            'M7646927': 'Theune, Mariet (UT-EEMCS) [researcher] [TCS]',
                            'M7716307': 'Varenhorst, Ivo (UT-EEMCS) [researcher] [TCS/EE]',
                            'M7666116': 'Bemthuis, Rob (UT-EEMCS) [researcher] [TCS]',
                            'M7700606': 'Chen, Kuan (UT-EEMCS) [researcher] [TCS/EE]',
                            'M7695442': 'Le Viet Duc, Duc (UT-EEMCS) [researcher] [TCS]',
                            'M7668390': 'Atashgahi, Zahra (UT-EEMCS) [researcher] [TCS]',
                            'M7664330': 'Seifert, Christin (UT-EEMCS) [researcher] [TCS]',
                            'M7700813': 'Rook, Jeroen (UT-EEMCS) [researcher] [TCS]',
                            'M7717102': 'Khadka, Shyam Krishna (UT-EEMCS) [researcher] [TCS/EE]',
                            'M7642982': 'Rijswijk-Deij, Roland van (UT-EEMCS) [researcher] [TCS/EE]',
                            'M7700625': 'Nguyen, Minh Son (UT-EEMCS) [researcher] [TCS]',
                            'M7664572': 'Ham-de Vos, Jeroen van der (UT-EEMCS) [researcher] [TCS/EE]',
                            'M7668017': 'Sarmah, Dipti (UT-EEMCS) [researcher] [TCS]',
                            'M7647139': 'Veldhuis, Raymond (UT-EEMCS) [researcher] [TCS]',
                            'M7704167': 'Gillani, Ghayoor (UT-EEMCS) [researcher] [TCS/EE]',
                            'M7668807': 'Haq, Yasir (UT-BMS) [researcher] [BMS]',
                            'M7669053': 'Rangel Carneiro Magalhaes, Syllas (UT-EEMCS) [researcher] [TCS/EE]',
                            'M7700537': 'Talavera Martínez, Estefanía (UT-EEMCS) [researcher] [TCS]',
                            'M7641472': 'Charlotte Bijron (UT-EEMCS) [secretary] [TCS]',
                            'M7685339': 'Bonino da Silva Santos, Luiz (UT-EEMCS) [researcher] [TCS]',
                            'M7666125': 'Klein Brinke, Jeroen (UT-EEMCS) [researcher] [TCS]',
                            'M7667040': 'Strisciuglio, Nicola (UT-EEMCS) [researcher] [TCS]',
                            'M7667908': 'Epa Ranasinghe, Champika (UT-EEMCS) [researcher] [TCS]',
                            'M7696840': 'Ludden, Geke (UT-ET) [researcher] [ET]',
                            'M7700254': 'Zia, Kamran (UT-EEMCS) [researcher] [TCS]',
                            'M7712247': 'Simonetto, Stefano (UT-EEMCS) [researcher] [TCS]',
                            'M7643214':'Reidsma, Dennis (UT-EEMCS) [researcher] [TCS]',
                            'M7664627':'Anbalagan, Sabari (UT-EEMCS) [researcher] [TCS]',
                            'M7667487':'Continella, Andrea (UT-EEMCS) [researcher] [TCS]',
                            'M7668233':'Zaytsev, Vadim (UT-EEMCS) [researcher] [TCS]',
                            'M7667464':'Parmentier, Jeanne (UT-EEMCS)  [researcher] [TCS]',
                            'M7704049':'Elhajj, Mohammed (UT-EEMCS) [researcher] [TCS]',
                            'M7640854':'Nijholt, Anton (UT-EEMCS) [researcher] [TCS]',
                            'M7686221':'Delden, Robby van (UT-EEMCS) [researcher] [TCS]',
                            'M7667299':'Lucas, Peter (UT-EEMCS) [researcher] [TCS]',
                            'M7667961':'Mocanu, Decebal (UT-EEMCS) [researcher] [TCS]',
                            'M7700795':'Ottavi, Marco (UT-EEMCS) [researcher] [TCS/EE]',
                            'M7662267':'Hartmanns, Arnd (UT-EEMCS) [researcher] [TCS]',
                            'M7666824':'Hahn, Florian (UT-EEMCS) [researcher] [TCS]',
                            'M7714536':'Veugen, Thijs (UT-EEMCS) [researcher] [TCS]',
                            'M7663995':'Riemsdijk, Birna van (UT-EEMCS) [researcher] [TCS]',
                            'M7667012':'Bassit, Amina (UT-EEMCS)  [researcher] [TCS]',
                            'M7713038':'Wu, Boqian (UT-EEMCS) [researcher] [TCS]',
                            'M7667825':'Huang, Yanqiu (UT-EEMCS) [researcher] [TCS]',
                            'M7668420':'Nicoletti, Stefano (UT-EEMCS) [researcher] [TCS]',
                            'M7667518':'Bos, Petra van den (UT-EEMCS) [researcher] [TCS]',
                            'M7699285':'Weda, Judith (UT-EEMCS) [researcher] [TCS]',
                            'M7647830':'Berg, Hans van den (UT-EEMCS) [researcher] [TCS/EE]',
                            'M7668208':'Alachiotis, Nikolaos (UT-EEMCS) [researcher] [TCS/EE]',
                            'M7681336':'Daneva, Maya (UT-EEMCS) [researcher] [TCS/EE]',
                            'M7667837':'Stuldreher, Ivo (UT-EEMCS) [researcher] [TCS]',
                            'M7668234':'Zangiabady, Mahboobeh (UT-EEMCS) [researcher] [TCS/EE]',
                            'M7669085':'Yeleshetty, Deepak (UT-EEMCS) [researcher] [TCS]',
                            'M7661572':'Wienen, Hans (UT-EEMCS) [researcher] [TCS]',
                            'M7668561':'Haandrikman, Marleen (UT-BMS) [researcher] [BMS]',
                            'M7667614':'Weedage, Lotte (UT-EEMCS) [researcher] [MATH]',
                            'M7707381':'Chen, Ting-Han (UT-EEMCS) [researcher] [TCS]',
                            'M7700794':'Dummer, Sven (UT-EEMCS) [researcher] [MATH]',
                            'M7642276':'Olthof, Dorette (UT-ET) [researcher] [ET]',
                            'M7706307':'Tarahomi Yousofi Sherbaf, Sousan (UT-EEMCS) [researcher] [TCS/EE]',
                            'M7668805':'Fasya, Evania (UT-EEMCS) [researcher] [TCS]',
                            'M7666231':'Piest, Sebastian (UT-BMS) [researcher] [BMS]',
                            'M7661509':'Englebienne, Gwenn (UT-EEMCS) [researcher] [TCS]',
                            'M7664709':'Califano, Federico (UT-EEMCS) [researcher] [EE]',
                            'M7709082':'Rezaei, Tina (UT-EEMCS) [researcher] [TCS/EE]',
                            'M7666819':'Mocanu, Elena (UT-EEMCS) [researcher] [TCS]',
                            'M7700544':'Trautmann, Heike (UT-EEMCS) [researcher] [TCS]',
                            'M7666721':'Batskos, Ilias (UT-EEMCS) [researcher] [TCS]',
                            'M7725996':'Klaassen, Fiona (UT-EEMCS) [secretary] [TCS]',
                            'M7666717':'Postma, Dees (UT-EEMCS) [researcher] [TCS]',
                            'M7691622':'Alveringh, Dennis (UT-EEMCS) [researcher] [EE]',
                            'M7664997':'Nagel, Joanneke van der (UT-EEMCS) [researcher] [TCS]',
                            'M7663524':'Bucur, Doina (UT-EEMCS) [researcher] [TCS]',
                            'M7667278':'Sharma, Nikita (UT-ET) [researcher] [ET]',
                            'M7641513':'Kuipers-Beld, Judith (UT-EEMCS) [researcher] [EE]',
                            'M7668405':'Gibb, Caroline (UT-EEMCS) [researcher] [TCS]',
                            'M7700953':'Mevissen, Sigert (UT-EEMCS) [researcher] [EE]',
                            'M7720410':'Papenmeier, Andrea (UT-EEMCS) [researcher] [TCS]',
                            'M7667715':'Chiumento, Alex (UT-EEMCS) [researcher] [TCS]',
                            'M7684566':'Truong, Khiet (UT-EEMCS) [researcher] [TCS]',
                            'M7663691':'Karahanoglu, Armagan (UT-ET) [researcher] [ET]',
                            'M7682816':'Spreeuwers, Luuk (UT-EEMCS) [researcher] [EE]',
                            'M7667276':'Sadeghi, Ehsan (UT-EEMCS) [researcher] [EE]',
                            }

    def run(self):
        #self.mongoclient.get_io_loop().run_until_complete(self.load_reports())
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
        COLORS = {
            "during": "rgb(13,25,35)",    # Subtle dark blue
            "after": "rgb(15,25,15)",     # Subtle dark green
            "before": "rgb(25,15,15)"     # Subtle dark red
        }
        def styled_title(text, color):
            return f"[{color}]{text}[/{color}]"

        def create_table(title):
            return table.Table(title=title, show_header=True, header_style="bold magenta", box=box.SIMPLE)

        def colored_panel(content, title=None, color=None, expand=True):
            return panel.Panel(content, title=title, expand=expand, style=Style(bgcolor=color))

        beforepilot = self.mongoclient['eemcs_pure_report_before_pilot_tcs.csv']
        duringpilot = self.mongoclient['eemcs_pure_report_midterm_pilot_23-04-2024.csv']
        afterpilot = self.mongoclient['eemcs_pure_report_final_pilot_26-06-2024.csv']
        oldpapers = []
        midpapers = []
        newpapers = []
        monthdatalist = list()
        oldpureids = set()
        midpureids = set()
        newpureids = set()
        pureids = set()
        comparisonlist = []
        async for item in duringpilot.find():
            created = datetime.strptime(item['date_created'][0:10], '%Y-%m-%d')
            if created < datetime(2024, 1, 1) and created > datetime(2022, 12, 31):
                if item['pureid'] not in oldpureids:
                    comparisonlist.append(item)
                    monthdatalist.append(created)
                    oldpureids.add(item['pureid'])
            elif (created > datetime(2023, 12, 31)) and (created < datetime(2024, 4, 24)) and (item['pureid'] not in oldpureids) and (item['pureid'] not in pureids):
                monthdatalist.append(created)
                pureids.add(item['pureid'])
                if item['creator'] in self.library_employees:
                    item['pilot_paper'] = True
                else:
                    item['pilot_paper'] = False
                midpapers.append(item)
                pureids.add(item['pureid'])



        async for item in afterpilot.find():
            created = datetime.strptime(item['date_created'][0:10], '%Y-%m-%d')
            if created < datetime(2024, 1, 1) and created > datetime(2022, 12, 31):
                if item['pureid'] not in oldpureids:
                    comparisonlist.append(item)
                    oldpureids.add(item['pureid'])
            elif (created > datetime(2023, 12, 31)) and (item['pureid'] not in oldpureids) and (item['pureid'] not in pureids):
                monthdatalist.append(created)
                pureids.add(item['pureid'])
                if item['creator'] in self.library_employees:
                    item['pilot_paper'] = True
                else:
                    item['pilot_paper'] = False
                newpapers.append(item)
        print(len(comparisonlist),len(midpapers), len(newpapers))
        monthmapping = {1 : 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Aug', 9: 'Sep',
                        10: 'Oct', 11: 'Nov', 12: 'Dec'}
        data_per_month = {2023: {}, 2024: {}}
        for year in range(2023, 2025):
            for month in range(1, 13):
                data_per_month[year][monthmapping[month]] = sum(
                    [1 for x in monthdatalist if x.month == month and x.year == year])
        print(data_per_month)
        listnum = 0
        charts = []
        statstables = []
        titles = []
        idtables = []
        publishertables = []
        grouptables = []
        roletables = []
        not_in_mapping = set()
        for paperset in [comparisonlist, midpapers, newpapers]:
            listnum += 1
            listname = ''
            yearstr = ''
            curcolor = ''
            if listnum == 1:
                listname = ''
                yearstr = '2023'
                curcolor = 'red'
            elif listnum == 2:
                listname = '1/1 -> 23/4'
                yearstr = '2024'
                curcolor = 'cyan'
            elif listnum == 3:
                listname = '23/4 -> 26/6'
                yearstr = '2024'
                curcolor = 'green'
            try:
                ids = [x['creator'] for x in paperset]
            except Exception as e:
                print(e)
                print(paperset)
                print(ids)
                print(listname, yearstr)
                print(listnum)
                raise e

            if len(ids) == 0:
                print(ids)
                print(paperset)
                raise Exception('No ids found')
            publishers = defaultdict(int)
            for paper in paperset:
                publishers[paper['publisher_journal']] += 1
            publishers = sorted(publishers.items(), key=lambda x: x[1], reverse=True)
            counts = defaultdict(int)
            pergroup = defaultdict(int)
            perrole = defaultdict(int)
            idlist = []
            for id in ids:
                counts[id] += 1
            try:
                for id, count in counts.items():
                    if id not in self.namemapping:
                        not_in_mapping.add(id)
                    idlist.append({'id'     : id,
                                   'name'   : self.namemapping[id].split('(')[0] if id in self.namemapping else '-',
                                   'faculty': self.namemapping[id].split('(UT-')[1].split(')')[
                                       0] if id in self.namemapping else '-',
                                   'group'  : self.namemapping[id].split('[')[2].split(']')[
                                       0] if id in self.namemapping else '-',
                                   'role'   : self.namemapping[id].split('[')[1].split(']')[
                                       0] if id in self.namemapping else 'researcher',
                                   'count'  : count
                                   })
            except Exception as e:
                print(e)
                print(id, count)
                print(self.namemapping[id])

            idlist.sort(key=lambda x: x['count'], reverse=True)
            idtable = create_table(styled_title(f'{yearstr} {listname} | Papers entered by ...', curcolor))
            idtable.add_column('id', justify='right', style='dim')
            idtable.add_column('name', justify='left', style='yellow', overflow='elliTCSis')
            idtable.add_column('faculty', justify='left', style='dim')
            idtable.add_column('group', justify='left', style='dim')
            idtable.add_column('role', justify='left', style='green')
            idtable.add_column('', justify='right', style='cyan')

            pergroup = defaultdict(int)
            perrole = defaultdict(int)
            grouplist = []
            rolelist = []
            for item in idlist:
                if item['role'] and (item['role'] != '-'):
                    perrole[item['role']] += 1*int(item['count'])
                    rolelist.append(item['role'])
                elif item['role'] == '-':
                    perrole['...'] += 1*int(item['count'])
                    rolelist.append('...')

                if item['group'] and (item['group'] != '-'):
                    pergroup[item['group']] += 1*int(item['count'])
                    grouplist.append(item['group'])
                elif item['group'] == '-':
                    pergroup['...'] += 1*int(item['count'])
                    grouplist.append('...')

            #sort the perrole and pergroup dicts based on the values
            perrole = {k:v for k,v in sorted(perrole.items(), key=lambda item: item[1], reverse=True)}
            pergroup = {k:v for k,v in sorted(pergroup.items(), key=lambda item: item[1], reverse=True)}


            grouplist = sorted(list(set(grouplist)), key=lambda x: x.lower())
            rolelist = sorted(list(set(rolelist)), key=lambda x: x.lower())

            grouptable = create_table('')
            grouptable.add_column('group', justify='left', style='yellow', overflow='elliTCSis')
            grouptable.add_column('#', justify='right', style='cyan')
            for item in pergroup.items():
                grouptable.add_row(*[str(i) for i in [item[0], item[1]]])
            grouptables.append(grouptable)
            roletable = create_table('')
            roletable.add_column('role', justify='left', style='yellow', overflow='elliTCSis')
            roletable.add_column('#', justify='right', style='cyan')
            for item,count in perrole.items():
                roletable.add_row(*[str(i) for i in [item, count]])
            roletables.append(roletable)

            publishertable = create_table('')
            publishertable.add_column('', justify='left', style='yellow', overflow='elliTCSis')
            publishertable.add_column('#', justify='right', style='cyan')
            for item in publishers:
                publishertable.add_row(*[str(i) for i in item])
            publishertables.append(publishertable)
            for item in idlist:
                idtable.add_row(*[str(i) for i in item.values()])
            idtables.append(idtable)
            if listnum == 2:
                days = datetime(2024, 5, 1) - datetime(2024, 1, 1)
                numpapers = len(paperset)
                papers_per_day = round(numpapers / days.days, 1)
                charts.append(termcharts.bar(data_per_month[2024], rich=True, mode='v'))
                titles.append(f'[{curcolor}]{year} | {listname}[/{curcolor}]: ~{papers_per_day} per day')
            elif listnum == 1:
                days = datetime(2023, 12, 31) - datetime(2023, 1, 1)
                numpapers = len(paperset)
                papers_per_day = round(numpapers / days.days, 1)
                charts.append(termcharts.bar(data_per_month[2023], rich=True, mode='v'))
                titles.append(f'[{curcolor}]2023 | 1/1 -> 31/12[/{curcolor}] ~{papers_per_day} per day')
            elif listnum == 3:
                days = datetime(2024, 6, 26) - datetime(2024, 4, 23)
                numpapers = len(paperset)
                papers_per_day = round(numpapers / days.days, 1)
                titles.append(f'[{curcolor}]{year} | {listname}[/{curcolor}] ~{papers_per_day} per day')
                charts.append(termcharts.bar(data_per_month[2024], rich=True, mode='v'))
            nums = {}
            for item in [['Article', 'Preprint'], ['Conference contribution', 'Conference article']]:
                nums[item[0]] = sum([1 for i in paperset if i['item_type'] in item])
            nums['Other'] = len(paperset) - nums['Article'] - nums['Conference contribution']
            statstable = create_table('')
            statstable.add_column('', justify='left', style='yellow')
            statstable.add_column('#', justify='center', style='cyan')
            statstable.add_column('%', justify='center', style='green')
            statstable.add_row('total', str(len(ids)), '-')
            statstable.add_row('by library backoffice',
                               str(sum([i['count'] for i in idlist if i['role'] == 'library'])),
                               str(round(sum([i['count'] for i in idlist if i['role'] == 'library']) * 100 / len(ids))) + '%'
                               )
            if listnum != 1:
                comparedate = datetime(2023, 10, 1)
                compareyear = 2024
            else:
                comparedate = datetime(2022, 10, 1)
                compareyear = 2023
            num_backfill = 0
            no_data = 0
            for i in paperset:
                try:
                    date = datetime.strptime(i['date_published'], '%Y-%m-%d')
                    if date < comparedate:
                        num_backfill += 1
                except Exception as e:
                    try:
                        date = datetime.strptime(i['date_earliest_published'], '%Y-%m-%d')
                        if date < comparedate:
                            num_backfill += 1
                    except Exception as e:
                        try:
                            date = int(year)
                            if year < compareyear:
                                num_backfill += 1
                        except Exception as e:
                            no_data +=1

            print(no_data, num_backfill)
            statstable.add_row('backfill', str(num_backfill), str(round(num_backfill * 100 / len(ids))) + '%')
            statstable.add_row('articles', str(nums['Article']), str(round(nums['Article'] * 100 / len(ids))) + '%')
            statstable.add_row('conference papers', str(nums['Conference contribution']),
                               str(round(nums['Conference contribution'] * 100 / len(ids))) + '%')
            statstable.add_row('others', str(nums['Other']), str(round(nums['Other'] * 100 / len(ids))) + '%')
            statstables.append(statstable)
        from rich.columns import Columns
        from rich.terminal_theme import SVG_EXPORT_THEME

        main_layout = layout.Layout()
        main_layout.split_column(
            layout.Layout(name="charts", ratio=10),
            layout.Layout(name="stats_tables", ratio = 6),
            layout.Layout(name="group_and_role_tables", ratio = 4)
        )

        # Charts layout
        main_layout["charts"].split_row(
            layout.Layout(name="chart_2024"),
            layout.Layout(name="chart_2023")
        )

        # Stats tables layout
        main_layout["stats_tables"].split_row(
            layout.Layout(name="stats_2024_during"),
            layout.Layout(name="stats_2024_after"),
            layout.Layout(name="stats_2023")
        )

        # Group and role tables layout
        main_layout["group_and_role_tables"].split_row(
            layout.Layout(name="group_role_2024_during"),
            layout.Layout(name="group_role_2024_after"),
            layout.Layout(name="group_role_2023")
        )

        # Update layout with content

        main_layout["chart_2024"].update(colored_panel(charts[1], title=styled_title("Papers/month 2024", "cyan"), color=COLORS['during'], expand=True))
        main_layout["chart_2023"].update(colored_panel(charts[0], title=styled_title("Papers/month 2023", "red"), color=COLORS["before"], expand=True))

        main_layout["stats_2024_during"].update(colored_panel(statstables[1], title=titles[1], color=COLORS["during"], expand=True))
        main_layout["stats_2024_after"].update(colored_panel(statstables[2], title=titles[2], color=COLORS["after"], expand=True))
        main_layout["stats_2023"].update(colored_panel(statstables[0], title=titles[0], color=COLORS["before"], expand=True))


        main_layout["group_role_2024_during"].update(
            colored_panel(Columns([grouptables[1], roletables[1]], align='center', expand=True), title=styled_title("items added by", "cyan"), color=COLORS["during"], expand=True)
        )
        main_layout["group_role_2024_after"].update(
            colored_panel(Columns([grouptables[2], roletables[2]] , align='center', expand=True), title=styled_title("items added by", "green"), color=COLORS["after"], expand=True)
        )
        main_layout["group_role_2023"].update(
            colored_panel(Columns([grouptables[0], roletables[0]], align='center', expand=True), title=styled_title("items added by", "red"), color=COLORS["before"], expand=True)
        )

        # Print and save the layout
        cons = console.Console(record=True)
        cons.print(main_layout)
        cons.save_svg("improved_layout.svg", title="Improved Pilot Update Layout", theme=SVG_EXPORT_THEME)
        for i in not_in_mapping:
            print(f"'{i}':'',")
        '''
        # old layout
        lay = layout.Layout()
        lay.split_column(
            layout.Layout(name='charts'),
            layout.Layout(name='tables'),

        )
        lay['tables'].split_row(
            layout.Layout(name='table1'),
            layout.Layout(name='table2'),
            layout.Layout(name='table3'),
        )
        lay['charts'].split_row(
            layout.Layout(name='chart1', ratio=2),
            layout.Layout(name='chart2', ratio=1),
        )


        lay['chart1'].update(panel.Panel(Columns([charts[2]], align='center'), title='papers/month [green]20[/green][cyan]24[/cyan]'))
        lay['chart2'].update(panel.Panel(Columns([charts[0]], align='center'), title='papers/month [red]2023[/red]'))
        lay['table1'].update(panel.Panel(Columns([statstables[0]], align='center'), title=titles[0]))
        lay['table2'].update(panel.Panel(Columns([statstables[1]], align='center'), title=titles[1]))
        lay['table3'].update(panel.Panel(Columns([statstables[2]], align='center'), title=titles[2]))
        cons = console.Console(record=True)
        cons.print(lay)
        lay2 = layout.Layout(
        )
        lay2.split_column(
            layout.Layout(name='grouptables'),

        )
        lay2['grouptables'].split_row(
            layout.Layout(name='during'),
            layout.Layout(name='after'),
            layout.Layout(name='before'),

        )
        lay2['before'].update(panel.Panel(Columns([grouptables[0], roletables[0]], align='center'), title='[red]all of 2023[/red]'))
        lay2['during'].update(panel.Panel(Columns([grouptables[1], roletables[1]], align='center'), title='[cyan]during pilot[/cyan]'))
        lay2['after'].update(panel.Panel(Columns([grouptables[2], roletables[2]], align='center'), title='[green]after pilot[/green]'))

        cons.print(lay2)
        cons.save_svg("example.svg", title="Pure pilot update", theme=SVG_EXPORT_THEME)

        for i in range(len(idtables)):
            cons.print(idtables[i])
        '''

