import pymongo
from django.conf import settings
from rich import print
from rich.console import Console
from rich.table import Table

MONGOURL = getattr(settings, "MONGOURL")
MONGODB=pymongo.MongoClient(MONGOURL)
db=MONGODB["mus"]
authors_ut_people = db["api_responses_UT_authors_peoplepage"]
cons = Console()

def check_peoplepage(skip=True):
    def maketable(docs: list) -> Table:
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("#", style='cyan')
            table.add_column("Review Status", justify="left", style="green", no_wrap=True)
            table.add_column("Searchname", style='red')
            table.add_column("Found name", style='yellow')
            table.add_column("Email")
            table.add_column("Score")
            for num,doclist in enumerate(docs):
                check = doclist[1]
                if check == 'review':
                    check = ':question_mark: [dark_orange]review[/dark_orange]'
                if check == 'delete':
                    check = ':x: [red]delete[/red]'
                if check == 'passed':
                    check = ':white_heavy_check_mark: [green]passed[/green]'
                if not check:
                    check = ':green_square: [cyan]not checked[/cyan]'
                doc = doclist[2]
                table.add_row(str(num+1), check, doc["searchname"],doc["foundname"],doc["email"],str(doc["score"]) )
            cons.print(table)
        
    docs = []
    batchlen=8
    stop=False
    updated=False
    i=0
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

            while busy:
                if updated:
                    maketable(docs)
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
                break
            if updated:
                maketable(docs)
                cons.print('\n')
            
            docs = []
            i=0
            updated=False
                    
        


def main():
    if __name__ == "__main__":
        check_peoplepage()