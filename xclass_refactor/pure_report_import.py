
import motor.motor_asyncio
from django.conf import settings
from collections import defaultdict
import pandas as pd
import csv
import aiometer
from rich import print, console, table
import openpyxl_dictreader
from zipfile import BadZipFile
class PureReport():
    def __init__(self, filenames: list[str] = None):
        MONGOURL = getattr(settings, "MONGOURL")
        self.mongoclient : motor.motor_asyncio.AsyncIOMotorClient = motor.motor_asyncio.AsyncIOMotorClient(MONGOURL).metadata_unificiation_system
        self.filenames : list[str] = filenames
        self.library_employees = ['M7731800',
                                    'M7642439'
                                    'M7642471',
                                    'M7641474',
                                    'M7640169',
                                ]
        self.namemapping = {'M7731800':'Schipper, Liene (UT-LISA) [library] [library]',
                            'M7642471':'Bevers, René (UT-LISA) [library] [library]',
                            'M7641474':'Leusink-Eikelboom, Yvonne (UT-LISA) [library] [library]',
                            'M7640169':'Bakker-Koorman, Karin (UT-LISA) [library] [library]',
                            'M7642439':'Exterkate-ten Heggeler, Yvonne (UT-LISA) [library] [library]',
                            'M7692738':'Scholten-Koop, Bertine (UT-EEMCS) [secretary] [SCS]',
                            'M7693261':'Steenbergen-Boeringa, Marion (UT-EEMCS) [secretary] [FMT]',
                            'M7640406':'Broersma, Hajo (UT-EEMCS) [researcher] [FMT]',
                            'M7668993':'Lopuhaä-Zwakenberg, Milan (UT-EEMCS) [researcher] [FMT]',
                            'M7660017':'Meuwly, Didier (UT-EEMCS) [researcher] [DMB]',
                            'M7688543':'Huisman, Marieke (UT-EEMCS) [researcher] [FMT]',
                            'M7687683':'Jonker, Mattijs (UT-EEMCS) [researcher] [DACS]',
                            'M7662106':'Bukhsh, Faiza (UT-EEMCS) [researcher] [DMB]',
                            'M7712831':'Prince Sales, Tiago (UT-EEMCS) [researcher] [SCS]',
                            'M7667645':'Wang, Shenghui (UT-EEMCS) [researcher] [HMI]',
                            'M7715214':'Miranda Soares, Filipi (UT-EEMCS) [researcher] [SCS]',
                            'M7680523':'Stoelinga, Mariëlle (UT-EEMCS) [researcher] [FMT]',
                            'M7660096':'Kamminga, Jacob (UT-EEMCS) [researcher] [PS]',
                            'M7663975':'Müller, Moritz (UT-EEMCS) [researcher] [DACS]',
                            'M7646927':'Theune, Mariet (UT-EEMCS) [researcher] [HMI]',
                            'M7716307':'Varenhorst, Ivo (UT-EEMCS) [researcher] [CAES]',
                            'M7666116':'Bemthuis, Rob (UT-EEMCS) [researcher] [PS]',
                            'M7700606':'Chen, Kuan (UT-EEMCS) [researcher] [CAES]',
                            'M7695442':'Le Viet Duc, Duc (UT-EEMCS) [researcher] [PS]',
                            'M7668390':'Atashgahi, Zahra (UT-EEMCS) [researcher] [DMB]',
                            'M7664330':'Seifert, Christin (UT-EEMCS) [researcher] [DMB]',
                            'M7700813':'Rook, Jeroen (UT-EEMCS) [researcher] [DMB]',
                            'M7717102':'Khadka, Shyam Krishna (UT-EEMCS) [researcher] [DACS]',
                            'M7642982':'Rijswijk-Deij, Roland van (UT-EEMCS) [researcher] [DACS]',
                            'M7700625':'Nguyen, Minh Son (UT-EEMCS) [researcher] [PS]',
                            'M7664572':'Ham-de Vos, Jeroen van der (UT-EEMCS) [researcher] [DACS]',
                            'M7668017':'Sarmah, Dipti (UT-EEMCS) [researcher] [SCS]',
                            'M7647139':'Veldhuis, Raymond (UT-EEMCS) [researcher] [DMB]',
                            'M7704167':'Gillani, Ghayoor (UT-EEMCS) [researcher] [CAES]',
                            'M7668807':'Haq, Yasir (UT-BMS) [researcher] [IEBIS]',
                            'M7669053':'Rangel Carneiro Magalhaes, Syllas (UT-EEMCS) [researcher] [DACS]',
                            'M7700537':'Talavera Martínez, Estefanía (UT-EEMCS) [researcher] [DMB]'
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
        beforepilot = self.mongoclient['eemcs_pure_report_before_pilot_tcs.csv']
        duringpilot = self.mongoclient['eemcs_pure_report_midterm_pilot_23-04-2024.csv']
        oldpapers = []
        newpapers = []
        pureids = set()
        async for item in beforepilot.find():
            oldpapers.append(item)
            pureids.add(item['pureid'])
        async for item in duringpilot.find():
            if item['pureid'] not in pureids:
                if item['creator'] in self.library_employees:
                    item['pilot_paper'] = True
                else:
                    item['pilot_paper'] = False
                newpapers.append(item)

        print('old papers', len(oldpapers))
        print('new papers', len(newpapers))
        ids = [x['creator'] for x in newpapers]
        counts = defaultdict(int)
        pergroup = defaultdict(int)
        perrole = defaultdict(int)
        idlist = []
        for id in ids:
            counts[id] += 1
        try:
            for id, count in counts.items():
                idlist.append({'id': id,
                        'name': self.namemapping[id].split('(')[0] if id in self.namemapping else '-',
                        'faculty': self.namemapping[id].split('(UT-')[1].split(')')[0] if id in self.namemapping else '-',
                        'group': self.namemapping[id].split('[')[2].split(']')[0] if id in self.namemapping else '-',
                        'role': self.namemapping[id].split('[')[1].split(']')[0] if id in self.namemapping else '-',
                        'count': count
                    })
        except Exception as e:
            print(e)
            print(id, count)
            print(self.namemapping[id])

        from rich.terminal_theme import MONOKAI

        idlist.sort(key=lambda x: x['count'], reverse=True)
        idtable = table.Table(title='Papers entered by ...', show_lines=True)
        idtable.add_column('id', justify='right', style='dim')
        idtable.add_column('name', justify='left', style='yellow')
        idtable.add_column('faculty', justify='left', style='dim')
        idtable.add_column('group', justify='left', style='dim')
        idtable.add_column('role', justify='left', style='green')
        idtable.add_column('# papers added', justify='right', style='cyan')

        for item in idlist:
            idtable.add_row(*[str(i) for i in item.values()])
            perrole[item['role']] += 1
            pergroup[item['group']] += 1
        cons = console.Console(record=True)
        statstable = table.Table(title_justify='center', title='Papers added to Pure for TCS groups between 6 March 2024 and 23 April 2024', show_lines=True)
        statstable.add_column('grouping', justify='left', style='yellow')
        statstable.add_column('# of papers added', justify='center', style='green')
        statstable.add_column('% of total', justify='center', style='cyan')
        statstable.add_row('total', str(len(ids)), '-')
        statstable.add_row('added by library', str(sum([i['count'] for i in idlist if i['role'] == 'library'])), str(round(sum([i['count'] for i in idlist if i['role'] == 'library'])*100/len(ids)))+'%')
        statstable.add_row('added by researchers', str(sum([i['count'] for i in idlist if i['role'] == 'researcher'])), str(round(sum([i['count'] for i in idlist if i['role'] == 'researcher'])*100/len(ids)))+'%')
        statstable.add_row('added by secretaries', str(sum([i['count'] for i in idlist if i['role'] == 'secretary'])), str(round(sum([i['count'] for i in idlist if i['role'] == 'secretary'])*100/len(ids)))+'%')

        cons.print(statstable)
        cons.print(idtable)

        cons.save_svg("example.svg", theme=MONOKAI)
