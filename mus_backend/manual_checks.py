import pymongo
from django.conf import settings
from rich import print
from rich.console import Console
from rich.table import Table

MONGOURL = getattr(settings, "MONGOURL")
MONGODB=pymongo.MongoClient(MONGOURL)
db=MONGODB["mus"]
authors_ut_people = db["api_responses_UT_authors_peoplepage"]
pure_report_start_tcs = db["pure_report_start_tcs"]
pure_report_ee = db["pure_report_ee"]
cons = Console()
def maketable(docs: list, inputparams: list, foundparams: list) -> Table:
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("#", style='cyan')
        table.add_column("Review Status", justify="left", style="green", no_wrap=True)
        for inputparam in inputparams:
            table.add_column(str(inputparam), style="red")
        for foundparam in foundparams:
            table.add_column(str(foundparam), style="yellow")
        getdatalist = []
        getdatalist.extend(inputparams)
        getdatalist.extend(foundparams)
        for num,single_doc in enumerate(docs):
            check = single_doc[1]
            if check == 'review':
                check = ':question_mark: [dark_orange]review[/dark_orange]'
            if check == 'delete':
                check = ':x: [red]delete[/red]'
            if check == 'passed':
                check = ':white_heavy_check_mark: [green]passed[/green]'
            if not check:
                check = ':green_square: [cyan]not checked[/cyan]'
            doc = single_doc[2]
            table.add_row(str(num+1), check, *[str(doc[x]) for x in getdatalist])
        cons.print(table)

def check_peoplepage():
    '''
    todo: implement this, now just a copy of check_purereports()
    '''
    docs = []
    batchlen=8
    stop=False
    updated=False
    skip = False
    i=0
    cons.rule('Checking PureReport <-> PureEntry matches', style='bold magenta')
    go = False
    inputparams = ["searchname"]
    foundparams = ["pure_entry_id", "email", "score"]
    while not go:
        cons.print('Enter [bold green4]s[/bold green4] to skip already checked items, [dark_orange bold]z[/dark_orange bold] to re-check all items, and [bold red]q[/bold red] to quit.')
        setting = cons.input(r':> ')
        if setting.lower() in ['s','z','q']:
            if setting.lower()=='s':
                skip = True
                go = True
            elif setting.lower()=='z':
                go = True
            elif setting.lower()=='q':
                cons.print('[bold red]Quitting.[/bold red]')
                return False
    if skip:
        cons.print('Skipping batches if all items are already processed.')
    totalitems= authors_ut_people.count_documents({})
    alreadychecked= authors_ut_people.count_documents({"manual_check":{"$exists":True}})
    percentage = alreadychecked*100/totalitems
    cons.print(f'Number of items in collection: [orchid]{totalitems}[/orchid]')
    cons.print(f'Number of items already checked: {alreadychecked} [medium_violet_red]({percentage:.2f}% done)[/medium_violet_red]')
    for doc in authors_ut_people.find().sort('score',pymongo.ASCENDING):
        i=i+1
        check = doc.get("manual_check","")
        docs.append([doc['_id'],check,doc])

        if i > batchlen:
            if skip:
                allchecks = ['empty' for doc in docs if doc[1]=='']
                if 'empty' in allchecks:
                    busy = True
                    updated=True
                else:
                    busy = False
                    updated=False
            else:
                busy = False
                updated=True

            if updated:
                maketable(docs, inputparams, foundparams)

                for i in range(len(docs)):
                    next = False
                    while not next:
                        cons.print(f'''Item {i+1}/{len(docs)}:
                                   {docs[i][2]['searchname']}
                                   {docs[i][2]['foundname']}
                                   ''')
                        cons.print('[orange_red1]z[/orange_red1]: review, [red3]x[/red3]: delete, [green4]c[/green4]: ok')
                        mark = cons.input(r':> ')
                        if mark.lower() in ['z','x','c']:
                            if mark.lower()=='z':
                                act='review'
                            elif mark.lower()=='x':
                                act='delete'
                            elif mark.lower()=='c':
                                act='passed'
                            next = True
                        else:
                            cons.print('[bold red]Invalid input. Please try again.[/bold red]')
                    cons.print(f'Marking item {i+1}/{len(docs)} as {act}')
                    authors_ut_people.update_one({'_id':docs[int(i)][0]},{'$set':{'manual_check':act}})
                    docs[int(i)][1] = act

            while busy:
                if updated:
                    maketable(docs, inputparams, foundparams)
                    updated=False
                cons.print(f'''
{'[orange_red1]z[/orange_red1], [red3]x[/red3]' : <5} Mark items for [orange_red1]review[/orange_red1]/[red3]deletion[/red3]
{'[spring_green3]n[/spring_green3]': <5} Mark all unchecked [spring_green3]passed[/spring_green3] and go to next set
{'[dodger_blue2]q[/dodger_blue2]': <5} Quit
                ''', justify="left")
                choice = cons.input(r':>  ')
                if choice.lower() in ['z','x']:
                    if choice.lower()=='z':
                        color = 'orange_red1'
                        act='review'
                    elif choice.lower()=='x':
                        color = 'red3'
                        act='delete'
                    num = cons.input(f'[{color}]{act}[/{color}] which #s? (ex. 123 or 6)\n')
                    if not num.isdecimal():
                        cons.print('[bold red]Invalid input. Please try again.[/bold red]')
                    else:
                        updated=True
                        for n in num:
                            n = int(n)-1
                            authors_ut_people.update_one({'_id':docs[int(n)][0]},{'$set':{'manual_check':act}})
                            docs[int(n)][1] = act

                elif choice.lower()=='n':
                    for doc in docs:
                        if not doc[1] or 'not checked' in doc[1]:
                            updated=True
                            authors_ut_people.update_one({'_id':doc[0]},{'$set':{'manual_check':'passed'}})
                            doc[1] = 'passed'
                        busy = False
                elif choice.lower()=='q':
                    busy = False
                    stop = True

            if stop:
                cons.print('Quitting check_peoplepage() without further updating this batch.')
                break
            if updated:
                maketable(docs, inputparams, foundparams)
                cons.print('\n')

            docs = []
            i=0
            updated=False

def check_purereports():
    docs = []
    batchlen=8
    stop=False
    updated=False
    skip = False
    i=0
    cons.rule('Checking OA <-> UT people page matches', style='bold magenta')
    go = False
    inputparams = ["searchname"]
    foundparams = ["foundname", "email", "score"]
    while not go:
        cons.print('Enter [bold green4]s[/bold green4] to skip already checked items, [dark_orange bold]z[/dark_orange bold] to re-check all items, and [bold red]q[/bold red] to quit.')
        setting = cons.input(r':> ')
        if setting.lower() in ['s','z','q']:
            if setting.lower()=='s':
                skip = True
                go = True
            elif setting.lower()=='z':
                go = True
            elif setting.lower()=='q':
                cons.print('[bold red]Quitting.[/bold red]')
                return False
    if skip:
        cons.print('Skipping batches if all items are already processed.')
    totalitems= authors_ut_people.count_documents({})
    alreadychecked= authors_ut_people.count_documents({"manual_check":{"$exists":True}})
    percentage = alreadychecked*100/totalitems
    cons.print(f'Number of items in collection: [orchid]{totalitems}[/orchid]')
    cons.print(f'Number of items already checked: {alreadychecked} [medium_violet_red]({percentage:.2f}% done)[/medium_violet_red]')
    for doc in authors_ut_people.find().sort('score',pymongo.ASCENDING):
        i=i+1
        check = doc.get("manual_check","")
        docs.append([doc['_id'],check,doc])

        if i > batchlen:
            if skip:
                allchecks = ['empty' for doc in docs if doc[1]=='']
                if 'empty' in allchecks:
                    busy = True
                    updated=True
                else:
                    busy = False
                    updated=False
            else:
                busy = False
                updated=True

            if updated:
                maketable(docs, inputparams, foundparams)

                for i in range(len(docs)):
                    next = False
                    while not next:
                        cons.print(f'''Item {i+1}/{len(docs)}:
                                   {docs[i][2]['searchname']}
                                   {docs[i][2]['foundname']}
                                   ''')
                        cons.print('[orange_red1]z[/orange_red1]: review, [red3]x[/red3]: delete, [green4]c[/green4]: ok')
                        mark = cons.input(r':> ')
                        if mark.lower() in ['z','x','c']:
                            if mark.lower()=='z':
                                act='review'
                            elif mark.lower()=='x':
                                act='delete'
                            elif mark.lower()=='c':
                                act='passed'
                            next = True
                        else:
                            cons.print('[bold red]Invalid input. Please try again.[/bold red]')
                    cons.print(f'Marking item {i+1}/{len(docs)} as {act}')
                    authors_ut_people.update_one({'_id':docs[int(i)][0]},{'$set':{'manual_check':act}})
                    docs[int(i)][1] = act

            while busy:
                if updated:
                    maketable(docs, inputparams, foundparams)
                    updated=False
                cons.print(f'''
{'[orange_red1]z[/orange_red1], [red3]x[/red3]' : <5} Mark items for [orange_red1]review[/orange_red1]/[red3]deletion[/red3]
{'[spring_green3]n[/spring_green3]': <5} Mark all unchecked [spring_green3]passed[/spring_green3] and go to next set
{'[dodger_blue2]q[/dodger_blue2]': <5} Quit
                ''', justify="left")
                choice = cons.input(r':>  ')
                if choice.lower() in ['z','x']:
                    if choice.lower()=='z':
                        color = 'orange_red1'
                        act='review'
                    elif choice.lower()=='x':
                        color = 'red3'
                        act='delete'
                    num = cons.input(f'[{color}]{act}[/{color}] which #s? (ex. 123 or 6)\n')
                    if not num.isdecimal():
                        cons.print('[bold red]Invalid input. Please try again.[/bold red]')
                    else:
                        updated=True
                        for n in num:
                            n = int(n)-1
                            authors_ut_people.update_one({'_id':docs[int(n)][0]},{'$set':{'manual_check':act}})
                            docs[int(n)][1] = act

                elif choice.lower()=='n':
                    for doc in docs:
                        if not doc[1] or 'not checked' in doc[1]:
                            updated=True
                            authors_ut_people.update_one({'_id':doc[0]},{'$set':{'manual_check':'passed'}})
                            doc[1] = 'passed'
                        busy = False
                elif choice.lower()=='q':
                    busy = False
                    stop = True

            if stop:
                cons.print('Quitting check_peoplepage() without further updating this batch.')
                break
            if updated:
                maketable(docs, inputparams, foundparams)
                cons.print('\n')

            docs = []
            i=0
            updated=False



def main():
        cons.rule('MUS Manual checking CLI', style='bold magenta')
        while True:
            selections = '''
            Select a task:
            [cyan]1.[/cyan] [green4](mongodb)[/green4] Check matches between OpenAlex authors and found UT matches
            [cyan]2.[/cyan] [green4](mongodb)[/green4] Check matches between PureReport entries and Pure OAI-PMH entries

            [bold red]q.[/bold red] Quit
            '''
            cons.print(selections)
            choice = cons.input(r':> ')
            if choice.lower() in ['1','2']:
                if choice.lower()=='1':
                    check_peoplepage()
                elif choice.lower()=='2':
                    check_purereports()
            elif choice.lower()=='q':
                cons.print('[bold red]Quitting.[/bold red]')
                break
            else:
                cons.print('[bold red]Invalid input. Please try again.[/bold red]')

if __name__ == "__main__":
    main()