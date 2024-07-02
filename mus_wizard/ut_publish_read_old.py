    async def add_openalex_work(self, data: dict, existing_work: Work | None = None):
        if data.get('id') in self.works:
            return
        type_crossref = data.get('type_crossref')
        work_type = None
        match type_crossref:
            case 'journal-article':
                work_type = WorkType.JOURNAL_ARTICLE
            case 'report':
                work_type = WorkType.JOURNAL_ARTICLE
            case 'journal-volume':
                work_type = WorkType.JOURNAL_ARTICLE
            case 'journal-issue':
                work_type = WorkType.JOURNAL_ARTICLE
            case 'journal':
                work_type = WorkType.JOURNAL_ARTICLE
            case 'proceedings-article':
                work_type = WorkType.CONFERENCE_PROCEEDING
            case 'proceedings-series':
                work_type = WorkType.CONFERENCE_PROCEEDING
            case 'proceedings':
                work_type = WorkType.CONFERENCE_PROCEEDING
            case 'book-chapter':
                work_type = WorkType.BOOK_CHAPTER
            case 'book-series':
                work_type = WorkType.BOOK
            case 'edited-book':
                work_type = WorkType.BOOK
            case 'reference-book':
                work_type = WorkType.BOOK
            case 'book-set':
                work_type = WorkType.BOOK
            case 'book':
                work_type = WorkType.BOOK
            case 'book-part':
                work_type = WorkType.BOOK_CHAPTER
            case _:
                work_type = WorkType.OTHER

        authors = []
        for authorsh in data.get('authorships'):
            author = authorsh.get('author')
            if author:
                if author.get('id') in self.authors:
                    auth = self.authors[author.get('id')]
                    if len(auth.groups) > 0:
                        authors.append(auth)
                else:
                    if authorsh.get('institutions'):
                        for institution in authorsh.get('institutions'):
                            if institution.get('ror') == ROR:
                                self.missing_authors.append(author)
        journal = None
        publisher = None
        if data.get('primary_location'):
            source = data.get('primary_location').get('source')
            if source:
                if source.get('host_organization'):
                    host_org_id: str = source.get('host_organization')
                    if host_org_id.startswith('https://openalex.org/P'):
                        pub_name = source.get('host_organization_name')
                        pub_id = host_org_id
                        publisher = await self.add_or_get_publisher(name=pub_name, id=pub_id)
                if (source.get('type') and source.get('type') == 'journal') or publisher:
                    journal_data = {
                            'name': source.get('display_name'),
                            'openalex_id': source.get('id'),
                            'publisher': publisher,
                            'issns': source.get('issn'),
                            'issn_l': source.get('issn_l'),
                        }
                    journal = await self.add_or_get_journal(data=journal_data)

        if not existing_work:
            work = Work(data_sources=[DataSource.OPENALEX],
                        openalex_id=data.get('id'),
                        authors=authors,
                        doi=await normalize_doi(data.get('doi')),
                        title=data.get('title'),
                        year=data.get('publication_year'),
                        type=work_type,
                        journals=[journal],
                        publishers=[publisher],)

        else:
            work = existing_work
            work.data_sources.append(DataSource.OPENALEX)
            work.openalex_id = data.get('id')
            if authors:
                if len(work.authors)>0:
                    authorlist = work.authors.copy()
                    authorlist.extend(authors)
                    unique_ids = set(map(id, authorlist))
                    uniquelist = []
                    for i in authorlist:
                        if id(i) in unique_ids:
                            uniquelist.append(i)
                            unique_ids.remove(id(i))
                    work.authors = uniquelist
                else:
                    work.authors = authors
            if not work.doi:
                work.doi = await normalize_doi(data.get('doi'))
            if not work.year:
                work.year = data.get('publication_year')
            if not work.type:
                work.type = work_type

                journal = None
                publisher = None
                if data.get('primary_location'):
                    source = data.get('primary_location').get('source')
                    if source:
                        if source.get('host_organization'):
                            host_org_id: str = source.get('host_organization')
                            if host_org_id.startswith('https://openalex.org/P'):
                                pub_name = source.get('host_organization_name')
                                pub_id = host_org_id
                                publisher = await self.add_or_get_publisher(name=pub_name, id=pub_id)
                        if (source.get('type') and source.get('type') == 'journal') or publisher:
                            journal_data = {
                                    'name': source.get('display_name'),
                                    'openalex_id': source.get('id'),
                                    'publisher': publisher,
                                    'issns': source.get('issn'),
                                    'issn_l': source.get('issn_l'),
                                }
                            journal = await self.add_or_get_journal(data=journal_data)
                if journal:
                    if not work.journals:
                        work.journals = [journal]
                    else:
                        work.journals.append(journal)
                if publisher:
                    if not work.publishers:
                        work.publishers = [publisher]
                    else:
                        work.publishers.append(publisher)

        self.works[work.openalex_id] = work
        if work.doi not in self.works:
            self.works[work.doi] = work

        self.flat_works.append(work)

    async def add_pure_work(self, data: dict, existing_work: Work | None = None):
        if data.get('internal_repository_id') in self.works:
            return

        authors = []
        if data.get('authors'):
            for auth in data.get('authors'):
                if auth.get('internal_repository_id') in self.authors:
                    auth = self.authors[auth.get('internal_repository_id')]
                    if len(auth.groups) > 0:
                        authors.append(auth)


        journals = []
        publishers = []

        if data.get('publishers'):
            for pub in data.get('publishers'):
                publishers.append(await self.add_or_get_publisher(name=pub))
        if data.get('issn'):
            issns = []
            issn_rawlist : list[dict[str,str]] = data.get('issn')
            for issn in issn_rawlist:
                issns.append(issn.values())
            for issn in issns:
                if issn in self.journals:
                    journals.append(self.journals[issn])
                else:
                    self.missing_issns.append(issn)
        pure_id = data.get('internal_repository_id')
        doi = await normalize_doi(data.get('doi'))
        title = data.get('title')
        year = data.get('publication_date')

        if not existing_work:
            work = Work(data_sources=[DataSource.PURE],
                        pure_id=pure_id,
                        authors=authors,
                        doi=doi,
                        title=title,
                        year=year,
                        journals=journals,
                        publishers=publishers,
                    )
        else:

            work = existing_work
            work.data_sources.append(DataSource.PURE)
            work.pure_id = data.get('internal_repository_id')
            if authors:
                if len(work.authors)>0:
                    authorlist = work.authors.copy()
                    authorlist.extend(authors)
                    unique_ids = set(map(id, authorlist))
                    uniquelist = []
                    for i in authorlist:
                        if id(i) in unique_ids:
                            uniquelist.append(i)
                            unique_ids.remove(id(i))
                    work.authors = uniquelist
                else:
                    work.authors = authors
            if not work.doi:
                work.doi = doi
            if not work.year:
                work.year = year
            if not work.title:
                work.title = title
            if not work.journals:
                work.journals = journals
            elif journals:
                work.journals.extend(journals)
            if not work.publishers:
                work.publishers = publishers
            elif publishers:
                work.publishers.extend(publishers)

        self.works[work.pure_id] = work
        if work.doi not in self.works:
            self.works[work.doi] = work
        self.flat_works.append(work)
    async def add_or_get_publisher(self, name: str, id: str | None = None) -> Publisher:
        if id and id in self.publishers:
            return self.publishers[id]
        elif name and name in self.publishers:
            return self.publishers[name]
        else:
            publisher = Publisher(name=name, openalex_id=id)
            self.publishers[publisher.openalex_id] = publisher
            self.publishers[publisher.name] = publisher
            self.publishers_flat.append(publisher)
            return publisher

    async def add_or_get_journal(self, data: dict) -> Journal:
        journal = None
        if data.get('openalex_id') and data.get('openalex_id') in self.journals:
            journal = self.journals[data.get('openalex_id')]
        elif data.get('issn_l') and data.get('issn_l')in self.journals:
            journal = self.journals[data.get('issn_l')]
        elif data.get('issns'):
            for issn in data.get('issns'):
                if issn and issn in self.journals:
                    co.print(f'Found journal in list by {issn}')
                    journal = self.journals[issn]
                    break
        elif data.get('name') and data.get('name') in self.journals:
            journal = self.journals[data.get('name')]

        if not journal:
            journal = Journal(name=data.get('name'), openalex_id=data.get('openalex_id'), publisher=data.get('publisher'), issns = data.get('issns'), issn_l=data.get('issn_l'))
            if journal.openalex_id:
                self.journals[journal.openalex_id] = journal
            self.journals[journal.name] = journal
            if journal.issn_l:
                self.journals[journal.issn_l] = journal
            if journal.issns:
                for issn in journal.issns:
                    self.journals[issn] = journal
            self.journals_flat.append(journal)

        if not journal.openalex_id and data.get('openalex_id'):
            journal.openalex_id = data.get('openalex_id')
            self.journals[journal.openalex_id] = journal
        if not journal.issn_l and data.get('issn_l'):
            journal.issn_l = data.get('issn_l')
            self.journals[journal.issn_l] = journal
        return journal


    async def add_works_by_author(self):
        # from the authorlist, grab all works by those people
        # use openalexid, orcid, etc
        ...

    async def get_work_data_from_openaire():
        # for each work in the list that doesn't have openaire id: pull data from openaire
        ...

    async def get_work_data_from_crossref():
        # for each doi query crossref
        ...
