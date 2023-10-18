import tkinter as tk
from tkinter.filedialog import askopenfilename
from tkinter import messagebox as tkmsg
from idlelib.tooltip import Hovertip
import re
import csv
import logging
import importoly
from dataclasses import dataclass
import dataclasses

# early to allow creating the IntVars inside ContestField
root = tk.Tk()
defaultColor = root.cget("bg")

@dataclass
class ContestField:
    displayname: str
    isSubcontest: bool
    allowEmpty: bool = False
    tooltip: str | None = None
    entry: tk.Entry = None
    isLocked: tk.IntVar = dataclasses.field(default_factory=tk.IntVar)

contestFields = {
    "name": ContestField("Contest name", False),
    "subject": ContestField("Subject", False),
    "type": ContestField("Type", False),
    "year": ContestField("Year", False),
    "subcontest_name": ContestField("Subcontest name", True),
    "class_range": ContestField("Class range", True, False, "Syntax: <name>,<min class>,<max class>"),
    "description": ContestField("Description", True, True),
}

@dataclass
class SpecialColumn:
    color: str
    coli: int | None = None
    ci: int = 0

specialColumnsN = {
    "placement": SpecialColumn("#dd3030"),
    "name": SpecialColumn("#30dd30"),
    "first name": SpecialColumn("#00aa00"),
    "last name": SpecialColumn("#10aa90"),
    "class": SpecialColumn("#7070dd"),
    "school": SpecialColumn("#41a5fc"),
    "instructors": SpecialColumn("#f78a2f"),
    "total": SpecialColumn("#ffcc00")
}

inferContest = {
    "subject": [
        {"pattern": "efo|fyysika|füüsika|fys", "value": "Füüsika"},
        {"pattern": "emo|mat|lvs|lvt", "value": "Matemaatika"},
        {"pattern": "eko|keemia", "value": "Keemia"},
        {"pattern": "inf", "value": "Informaatika"},
        {"pattern": "ego", "value": "Geograafia"},
        {"pattern": "ebo", "value": "Bioloogia"},
    ],
    "type": [
        {"pattern": "lv[0-9st]", "value": "Lahtine"},
        {"pattern": "lv", "value": "Lõppvoor"},
        {"pattern": "lah", "value": "Lahtine"},
    ],
    "class_range": [
        {"pattern": "(^|[^1-9])6k", "value": "6,6,6"},
        {"pattern": "(^|[^1-9])7k", "value": "7,7,7"},
        {"pattern": "(^|[^1-9])8k", "value": "8,8,8"},
        {"pattern": "(^|[^1-9])9k", "value": "9,9,9"},
        {"pattern": "10k", "value": "10,10,10"},
        {"pattern": "11k", "value": "11,11,11"},
        {"pattern": "12k", "value": "12,12,12"},
        {"pattern": "(^|[-_ ])g(ymn)?($|[-_.])", "value": "gümnaasium,10,12"},
        {"pattern": "(^|[-_ ])(pk?|pohikool)($|[-_.])", "value": "põhikool,8,9"},
        {"pattern": "(^|[-_ ])v(anem)?($|[-_.])", "value": "vanem,11,12"},
        {"pattern": "(^|[-_ ])n(oorem)?($|[-_.])", "value": "noorem,9,10"},
    ]
}

inferColumns = [
    {"pattern": r"(jrk|koht)\.?", "value": "placement"},
    {"pattern": r".*eesnimi", "value": "first name"},
    {"pattern": r".*pere(konna)?nimi", "value": "last name"},
    {"pattern": r"(õpilane|(õpilase )?nimi)\.?", "value": "name"},
    {"pattern": r"kool\.?", "value": "school"},
    {"pattern": r"kl(ass)?\.?", "value": "class"},
    {"pattern": r".*(juhendajad?|õp(etaja)?).*", "value": "instructors"},
    {"pattern": r".*kokku.*", "value": "total"},
]

deleteColumnColor = "#ffaaaa"


def warn(text: str):
    logging.warning(text)
    tkmsg.showwarning(message=text)


class ScrollableFrame(tk.Frame):
    def __init__(self, root, *args, **kwargs):
        self.root = root
        self.canvas = tk.Canvas(self.root)
        super().__init__(self.canvas, *args, **kwargs)
        self.canvas.create_window(0, 0, window=self, anchor=tk.NW)

        def onScroll(event):
            self.canvas.yview_scroll(-1 if event.num == 4 else 1, "units")

        self.canvas.bind_all("<Button-4>", onScroll)
        self.canvas.bind_all("<Button-5>", onScroll)

        self.bind("<Configure>", lambda *_: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

    def pack(self, *args, **kwargs):
        self.canvas.pack(*args, **kwargs)

    def setYScrollbar(self, scrollbar):
        scrollbar.configure(command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)

def setEntry(entry: tk.Entry, value: str):
    entry.delete(0, tk.END)
    entry.insert(0, value)

selectedField = None

def selectField(ri: int, ci: int):
    global selectedField
    if selectedField is not None:
        currentGrid[selectedField[0]][selectedField[1]].configure(font="sans 11")
    currentGrid[ri][ci].configure(font="sans 11 bold")
    selectedField = (ri, ci)
    setEntry(editField, currentGrid[ri][ci]["text"])

def fieldButton(ri: int, ci: int):
    def action(*_):
        selectField(ri, ci)
    return action

def clearGrid(clearSpecial=True):
    global selectedField

    for row in currentGrid:
        for field in row:
            field.destroy()
    currentGrid.clear()
    for field in gridHeader:
        field.destroy()
    gridHeader.clear()
    selectedField = None

    if clearSpecial:
        for sc in specialColumnsN.values():
            sc.coli = None

def deleteColumnAction(ci: int):
    def action(*_):
        # Delete the column
        grid = getGrid()
        for row in grid:
            del row[ci]

        setGrid(grid, False)

        # Update the special columns
        for sc in specialColumnsN.values():
            if sc.coli is None:
                pass
            elif sc.coli == ci:
                sc.coli = None
            elif sc.coli > ci:
                sc.coli -= 1
        highlightGrid()

    return action

"""
Set the grid to a 2D list of values
"""
def setGrid(grid: list[list[str]], clearSpecial=True):
    clearGrid(clearSpecial)

    if len(grid) == 0:
        return

    for ri, row in enumerate(grid):
        newRow = []
        currentGrid.append(newRow)
        for ci, field in enumerate(row):
            e = tk.Button(gridWrapper, text=field, command=fieldButton(ri, ci))
            e.grid(row=ri+1, column=ci, sticky="nsew")
            newRow.append(e)

    for ci in range(len(grid[0])):
        h = tk.Button(gridWrapper, text="Delete", command=deleteColumnAction(ci), background=deleteColumnColor)
        h.grid(row=0, column=ci)
        gridHeader.append(h)

"""
Get the grid as a 2D list of values
"""
def getGrid() -> list[list[str]]:
    grid = []
    for row in currentGrid:
        grid.append([])
        for v in row:
            grid[-1].append(v["text"])

    return grid

"""
Parse a CSV file into the editor
"""
def parseCSV(inFile):
    # read all of the data into a list
    reader = csv.reader(inFile, delimiter=",")
    newGrid = []
    maxLength = -1 # keep track of the max and min row lengths
    warnLengthMismatch = False
    for row in reader:
        # note: removing zero-width characters sometimes present in files
        fields = list(re.sub("[\ufeff]", "", f).strip() for f in row)
        newGrid.append(fields)
        length = len(fields)
        if length != maxLength:
            if maxLength != -1:
                warnLengthMismatch = True
            maxLength = max(maxLength, length)

    clearGrid()

    if warnLengthMismatch:
        warn("Row lengths are non-uniform!")
        # attempt to fix the problem
        for row in newGrid:
            row += ["" for _ in range(maxLength - len(row))]

    # import the data into the editor
    setGrid(newGrid)

"""
Infer the content of some fields based on the filename and column names
"""
def inferFields(filename: str):
    # Contest info

    for fieldName, patterns in inferContest.items():
        field = contestFields[fieldName]
        if not field.isLocked.get():
            for pattern in patterns:
                if re.search(pattern["pattern"], filename, re.IGNORECASE):
                    setEntry(field.entry, pattern["value"])
                    break

    # Special case for the year
    year = contestFields["year"]
    if not year.isLocked.get():
        m = re.search(r"(\D|^)(\d{4})(\D|$)", filename)
        if m:
            y1 = m.group(2)
            if int(y1) > 1900: # sanity check ig
                setEntry(year.entry, y1)

    # Columns
    for ci, name in enumerate(currentGrid[0]):
        for pattern in inferColumns:
            if re.match(pattern["pattern"], name["text"], re.IGNORECASE):
                specialColumnsN[pattern["value"]].coli = ci
                break
    highlightGrid()

lastOpenedFile: str = None
"""
"Open file" action performed
"""
def openFile():
    global lastOpenedFile
    # file dialog
    filename = askopenfilename(filetypes=[("CSV",".csv"), ("File", "*")])
    if filename == ():
        # cancelled
        return

    lastOpenedFile = filename
    reopenFile()

def reopenFile():
    print(lastOpenedFile)
    with open(lastOpenedFile) as inFile:
        parseCSV(inFile)

    inferFields(lastOpenedFile)
    highlightGrid()

def highlightGrid():
    # clear any highlighting
    for row in currentGrid:
        for field in row:
            field.configure(background=defaultColor)

    for sc in specialColumnsN.values():
        if sc.coli is not None:
            for row in currentGrid:
                row[sc.coli].configure(background=sc.color)

def substArithmetic(pattern: str, replacements: dict):
    # considered writing a bespoke templating engine
    # but f-strings are good enough
    fstring = 'f"""' + pattern + '"""'
    return eval(fstring, {}, replacements)

def importTable(*_):
    if any(field.entry.get() == "" and not field.allowEmpty
                for field in contestFields.values()):
        warn("Missing contest information")
        return

    sc = {col.coli: cname for cname, col in specialColumnsN.items() if col.coli is not None}
    coli = {cname: col.coli for cname, col in specialColumnsN.items()}

    if coli["placement"] is None:
        warn("Missing placement")
        return

    haveName, haveFirstName, haveLastName = (coli[x] is not None
                                             for x in ("name", "first name", "last name"))
    if haveName:
        if haveFirstName or haveLastName:
            warn("Extra name columns")
            return
    elif not (haveFirstName and haveLastName):
        warn("No name columns")
        return

    contestValues = {
        fname: field.entry.get()
        for fname, field in contestFields.items()
        if not field.isSubcontest
    }
    contest_name = substArithmetic(contestValues["name"], {'year': int(contestValues["year"])})
    contest = importoly.Contest(int(contestValues["year"]),
                                contestValues["subject"],
                                contestValues["type"],  contest_name, [])
    subcontest_classes = []
    if splitClass.get():
        if coli["class"] is None:
            warn("Need class column to split by class!")
            return
        subcontest_classes = {row[coli["class"]].split(",")[0] for row in list(getGrid())[1:]}
        print(subcontest_classes)
    else:
        subcontest_classes = [None]
    for subc_class in subcontest_classes:
        subcontestValues = {
            fname: field.entry.get().replace("$CLASS", subc_class or "")
            for fname, field in contestFields.items()
            if field.isSubcontest
        }

        class_range_name, *class_range = re.split(r"[ ,]", subcontestValues["class_range"])
        class_range = (int(class_range[0]), int(class_range[1]))
        subcontest_name = substArithmetic(subcontestValues["subcontest_name"], {'group': class_range_name})

        grid = getGrid()
        rows = iter(grid)
        header = next(rows)
        subcontest_columns = [field for i,field in enumerate(header) if i not in sc or sc[i] == "total"]
        subcontest = importoly.Subcontest(subcontest_name,
                class_range, class_range_name, subcontest_columns,
                [], subcontestValues["description"])
        for row in rows:
            cst_fields = []
            for ci, field in enumerate(row):
                if ci not in sc or sc[ci] == "total":
                    cst_fields.append(field.strip())

            instructors = ([] if coli["instructors"] is None else
                                         [x.strip() for x in re.split(r"[|,/]+", row[coli["instructors"]])
                                          if x.strip() != ""])
            placement = re.sub(r"[. ]", "", row[coli["placement"]])
            # fix tiebreaker notation like "3.-5."
            placement = re.sub(r"-\d+", "", placement)
            placement = int(placement) if placement else None
            cst_class = None if coli["class"] is None else row[coli["class"]].strip()
            if subc_class and cst_class != subc_class and cst_class:
                if cst_class.startswith(subc_class + ","):
                    cst_class = cst_class.removeprefix(subc_class + ",")
                else:
                    continue
            cst_class = int(cst_class) if cst_class else None
            cst_school = None if coli["school"] is None else row[coli["school"]].strip()

            # Name
            if haveName:
                nameParts = re.split(r"[, ]+", row[coli["name"]]) # type: ignore
            else:
                nameParts = [row[coli["first name"]], row[coli["last name"]]] # type: ignore

            nameParts = [part.strip() for part in nameParts if part.strip() != ""]

            if haveName and nameOrderRev.get():
                last = nameParts[0]
                del nameParts[0]
                nameParts.append(last)

            cst_name = " ".join(nameParts)

            contestant = importoly.Contestant(cst_name, cst_class, instructors,
                                              cst_school, placement, cst_fields)

            subcontest.contestants.append(contestant)
        contest.subcontests.append(subcontest)
    importoly.addContest(contest, bool(dryrunVal.get()))

# toolbar
toolbar = tk.Frame(root)
toolbar.pack(fill=tk.X, side=tk.TOP)
openButton = tk.Button(toolbar, text="Open", command=openFile)
openButton.pack(side='left')
reloadButton = tk.Button(toolbar, text="Reload", command=reopenFile)
reloadButton.pack(side='left')
reloadTip = Hovertip(reloadButton, "reload last-opened csv file", 100)
importButton = tk.Button(toolbar, text="Import", command=importTable)
importButton.pack(side='left')

dryrunVal = tk.IntVar()
dryrunCheck = tk.Checkbutton(toolbar, text="dry run", variable=dryrunVal)
dryrunCheck.pack(side='left')
dryrunTip = Hovertip(dryrunCheck, "rollback the db after insertion", 100)

# contest info
contestInfo = tk.Frame(root)
contestInfo.pack(fill=tk.X, after=toolbar)

for ci, cf in enumerate(contestFields.values()):
    tk.Label(contestInfo, text=cf.displayname).grid(row=0, column=ci)
    cf.entry = tk.Entry(contestInfo)
    cf.entry.grid(row=1, column=ci)
    if cf.tooltip is not None:
        Hovertip(cf.entry, cf.tooltip, 100)
    # wait you don't need to keep around these in a variable??
    ch = tk.Checkbutton(contestInfo, text="Lock", variable=cf.isLocked)
    ch.grid(row=2, column=ci)

# editor
editor = tk.Frame(root)
editor.pack(fill=tk.X, after=contestInfo)

editField = tk.Entry(editor)
editField.grid(row=0, column=0)

def applyEdit(*_):
    if selectedField is not None:
        currentGrid[selectedField[0]][selectedField[1]].configure(text=editField.get())

editField.bind("<Return>", applyEdit)

for ci, (scName, sc) in enumerate(specialColumnsN.items(), 1):
    sc.coli = None
    sc.ci = ci
    def createAction(sc):
        def action(*_):
            if selectedField is not None:
                sc.coli = selectedField[1]
                highlightGrid()
        return action

    def clearAction(sc):
        def action(*_):
            sc.coli = None
            highlightGrid()
        return action

    b = tk.Button(editor, text=f'Set "{scName}"', command=createAction(sc), background=sc.color)
    b.grid(row=0, column=ci)
    b2 = tk.Button(editor, text=f'Clear', command=clearAction(sc), background=sc.color)
    b2.grid(row=1, column=ci)

# Extra widgets
def genPlacementAction(*_):
    total = specialColumnsN["total"].coli
    if total is not None:
        placement = specialColumnsN["placement"].coli
        if placement is None:
            # Create the placement column
            grid = getGrid()
            rows = iter(grid)
            header = next(rows)
            header.insert(0, "Koht")
            for row in rows:
                row.insert(0, "0")

            setGrid(grid, False)

            # Increment the indices
            for sc in specialColumnsN.values():
                if sc.coli is not None:
                    sc.coli += 1

            specialColumnsN["placement"].coli = 0
            placement = 0
            total = specialColumnsN["total"].coli
            assert total is not None # pyright pls
            highlightGrid()

        classi = specialColumnsN["class"].coli
        if splitClass.get():
            if classi is None:
                warn("Need a class column to split by class!")
                return
            subcontests = {row[classi].split(",")[0] for row in list(getGrid())[1:]}
            print(subcontests)
        else:
            subcontests = [None]
        for subc_class in subcontests:
            # Calculate the placement
            lastS = float("inf")
            currPlace = 0
            startPlace = 0

            rows = iter(currentGrid)
            # Skip the header
            next(rows)
            for row in rows:
                if subc_class and row[classi]["text"] != subc_class and not row[classi]["text"].startswith(subc_class + ","):
                    continue
                s = float(row[total]["text"].replace(",", ".").replace('%',''))
                currPlace += 1
                if s < lastS:
                    row[placement].configure(text=str(currPlace))
                    lastS = s
                    startPlace = currPlace
                else:
                    row[placement].configure(text=str(startPlace))
genPlacementButton = tk.Button(editor, text='From "total"', command=genPlacementAction, background=specialColumnsN["placement"].color)
genPlacementButton.grid(row=2, column=specialColumnsN["placement"].ci)

nameOrderRev = tk.IntVar()
nameOrderRevCheck = tk.Checkbutton(editor, text="Reversed", variable=nameOrderRev)
nameOrderRevCheck.grid(row=2, column=specialColumnsN["name"].ci)
nameOrderTip = Hovertip(nameOrderRevCheck, "reverse name field\nmoves first word of name to the end", 100)

splitClass = tk.IntVar()
splitClassCheck = tk.Checkbutton(editor, text="split", variable=splitClass)
splitClassCheck.grid(row=2, column=specialColumnsN["class"].ci)
splitClassTip = Hovertip(splitClassCheck, "split into subcontests based on class\nuse $CLASS in subcontest params\nuse a,b in class to set age group=a, real class=b", 100)

# grid
gridWrapper = ScrollableFrame(root)
gridWrapper.pack(fill=tk.BOTH, expand=1, after=editor, side=tk.LEFT)

gridScrollY = tk.Scrollbar(root, orient=tk.VERTICAL)
gridScrollY.pack(fill=tk.Y, side=tk.RIGHT)
gridWrapper.setYScrollbar(gridScrollY)

currentGrid: list[list[tk.Button]] = []
gridHeader: list[tk.Button] = []

openFile()
tk.mainloop()
