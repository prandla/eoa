
"""
The main utility file for importing a contest (possibly just a single
subcontest). `addContest` should be about the only function used from this
module, as it is the only one that tries to manage the connection state and
errors properly.

Currently, no checks are performed for similar names (even ones with just
differing case), so duplicates might occur. Care should be taken especially
with contest and subcontest identifiers (year, subject, type, age group, name).
"""

import os
import json
import mysql.connector
import logging
from dataclasses import dataclass
import typing
# probably not ideal to use gui functions here but What Ever
from tkinter import messagebox as tkmsg

logging.basicConfig(level=logging.DEBUG)

# Credentials
with open(os.path.join(os.path.dirname(__file__),"../credentials.json")) as f:
    config = json.loads(f.read())
mysql_user = config["user"]
mysql_passwd = config["password"]
mysql_db = config["database"]
mysql_host = config["host"]

conn = mysql.connector.connect(user=mysql_user, password=mysql_passwd, database=mysql_db, host=mysql_host)
cur = conn.cursor()

logging.info('Running!')

@dataclass
class Contestant:
    name: str
    klass: typing.Optional[int]
    instructors: list[str]
    school: typing.Optional[str]
    placement: typing.Optional[int]
    fields: list[str]

@dataclass
class Subcontest:
    name: str
    class_range: tuple[int, int]
    class_range_name: str
    columns: list[str]
    contestants: list[Contestant]
    description: str

@dataclass
class Contest:
    year: int
    subject: str
    type: str
    name: str
    subcontests: list[Subcontest]

def info(msg):
    logging.info(msg)

def debug(msg):
    logging.debug(msg)

def execute(query, params):
    debug('Query: "' + query + '" ' + str(params))
    cur.execute(query, params)

"""
Create new record in the specified table

NOTE: use getMakeRow, as otherwise duplicates might be created
"""
def createRow(table, **params) -> int:
    paramsList = [(k, v) for k, v in params.items()]
    execute(f"INSERT INTO {table} (" + ', '.join((p[0] for p in paramsList)) + ") VALUES (" + ', '.join(['%s'] * len(paramsList)) + ")", tuple(p[1] for p in paramsList))
    assert isinstance(cur.lastrowid, int)
    return cur.lastrowid

# cache to prevent re-doing SELECTs on the same age_groups and schools all the time
row_cache: dict[tuple, int] = {}

"""
Get the id of a row in a table based on parameters
Insert that row if it does not exist
"""
def getMakeRow(table, confirmCreate = False, **params) -> int:
    # Get params as ordered list
    paramsList = [(k, v) for k, v in params.items()]
    if (table, *paramsList) in row_cache:
        debug("using cached row for " + str((table, *paramsList)))
        return row_cache[(table, *paramsList)]

    # Convert to statement and execute
    execute(f"SELECT id FROM {table} WHERE " + ' and '.join(p[0] + (' is %s' if p[1] is None else ' = %s') for p in paramsList) + ' LIMIT 1', tuple(p[1] for p in paramsList))

    # Return id if one was found
    for id, in cur:
        assert isinstance(id, int)
        row_cache[(table, *paramsList)] = id
        return id

    # Otherwise create that row
    if confirmCreate:
        if not tkmsg.askokcancel("importoly", f"Really insert new row into table {table}?\n{paramsList}"):
            raise Exception("Insertion canceled")
    result = createRow(table, **params)
    row_cache[(table, *paramsList)] = result
    return result

# separate from row_cache because we need to store info from 2 tables (sort of)
school_cache: dict[str, int] = {}
def getSchoolId(name: str) -> int:
    if name in school_cache:
        return school_cache[name]
    execute("SELECT id FROM school WHERE name = %s UNION SELECT correct FROM school_alias WHERE name = %s", (name, name))
    for id, in cur:
        assert isinstance(id, int)
        school_cache[name] = id
        return id
    res = createRow("school", name = name)
    school_cache[name] = res
    return res

def addContestant(contestant: Contestant, subcontestId: int, columnIds: list[int]):
    # Age group id could be NULL
    ageGroupId = None
    if contestant.klass is not None and contestant.klass != '':
        # Get age group
        ageGroupId = getMakeRow('age_group', confirmCreate=True,
                                name = contestant.klass,
                                min_class = contestant.klass,
                                max_class = contestant.klass)

    # Get person
    personId = getMakeRow('person', name = contestant.name)

    # Get school
    schoolId = None
    if contestant.school is not None and contestant.school != '':
        schoolId = getSchoolId(contestant.school)

    # Create contestant
    contestantId = createRow('contestant',
                         subcontest_id = subcontestId,
                         person_id = personId,
                         age_group_id = ageGroupId,
                         school_id = schoolId,
                         placement = str(contestant.placement or ''))

    # Create fields for contestant
    # these are inserted in batch later
    fieldsToInsert = []
    for c, v in zip(columnIds, contestant.fields):
        # (task_id, contestant_id, entry)
        fieldsToInsert.append((c, contestantId, str(v) if v is not None else None))

    # Create people for mentors
    mentorIds = [getMakeRow('person', name = m) for m in contestant.instructors]

    # Link mentors
    # same as with fields
    mentorsToInsert = []
    for m in mentorIds:
        # (contestant_id, mentor_id)
        mentorsToInsert.append((str(contestantId), str(m)))
    return fieldsToInsert, mentorsToInsert


def addSubcontest(subcontest: Subcontest, contestId: int):
    # Get age group
    ageGroupId = getMakeRow('age_group', confirmCreate=True,
                       name = subcontest.class_range_name,
                       min_class = subcontest.class_range[0],
                       max_class = subcontest.class_range[1])

    execute("SELECT id FROM subcontest WHERE contest_id = %s AND age_group_id = %s", (str(contestId), str(ageGroupId)))
    if cur.fetchone():
        raise Exception("this contest already has this subcontest")
    # Create subcontest
    subcontestId = createRow('subcontest',
                         contest_id = contestId,
                         age_group_id = ageGroupId,
                         name = subcontest.name,
                         description = subcontest.description)

    # Create columns
    columns = []
    for i, c in enumerate(subcontest.columns, 1):
        columns.append(createRow('subcontest_column',
                             subcontest_id = str(subcontestId),
                             name = c,
                             seq_no = i))

    fieldsToInsert = []
    mentorsToInsert = []
    # Create contestants
    for c in subcontest.contestants:
        res = addContestant(c, subcontestId, columns)
        fieldsToInsert += res[0]
        mentorsToInsert += res[1]
    if fieldsToInsert:
        query = "INSERT INTO contestant_field (task_id, contestant_id, entry) VALUES (%s, %s, %s)"
        debug('Query (executemany): "' + query + '" ' + str(fieldsToInsert))
        cur.executemany(query, fieldsToInsert)
    if mentorsToInsert:
        query = "INSERT INTO mentor (contestant_id, mentor_id) VALUES (%s, %s)"
        debug('Query (executemany): "' + query + '" ' + str(mentorsToInsert))
        cur.executemany(query, mentorsToInsert)


def addContest(contest: Contest, dryRun: bool = False):
    global row_cache, school_cache
    old_rowcache = row_cache.copy()
    old_schoolcache = school_cache.copy()
    try:
        # Get parameters
        typeId = getMakeRow('type', confirmCreate=True, name = contest.type)
        subjectId = getMakeRow('subject', confirmCreate=True, name = contest.subject)
        # Create contest
        execute("SELECT id, name FROM contest WHERE year = %s AND type_id = %s AND subject_id = %s", (contest.year, typeId, subjectId))
        if (row := cur.fetchone()):
            if not tkmsg.askokcancel("importoly", f"This contest already exists! use it?\n{row}"):
                raise Exception("insert canceled")
            contestId = row[0]
            assert isinstance(contestId, int)
        else:
            contestId = createRow('contest',
                                  year = contest.year,
                                  type_id = typeId,
                                  subject_id = subjectId,
                                  name = contest.name)

        # Create subcontests
        for sc in contest.subcontests:
            addSubcontest(sc, contestId)

        if dryRun:
            conn.rollback()
            info("Contest added (dry run)")
            row_cache = old_rowcache
            school_cache = old_schoolcache
        else:
            conn.commit()
            info("Contest added")
    except Exception as e:
        conn.rollback()
        row_cache = old_rowcache
        school_cache = old_schoolcache
        logging.exception(e)
        raise Exception()

