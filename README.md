Make these updates while giving me the project structure at the end
i need it to be a complete software with these changes(keeping python scripts for handling the functionalities )

In my app i need to be able to load xls,csv files 
show files as list where i can select the file and perform the following operations () on it

1-op to view and update/delete content of the table
2-op to convert it to table of debarquement(i will provide python script that do this gendeb.py )
3-op generate borderau of  reserve(genBorderaux.py)
4-op generate pvs of ships daily (tp to be set manually on deb ,+ damaged) (genPvs.py)
5-make a global database.xlsx where all ships are stored within it.
6-create a map module where i can set positions of ships on the dock (map of port djendjen jiel i will provide a clear picture of it),
 -on the same map i need to be able to put/edit/mv/delete marchandies on different positions ,the map should contain a legende where i will be able to show and hide different clients ,marchandies type,
7-a list of usual/mostly used files word,excel files .
8- a small page for tools such as calculating the surface marchandise took on land (depending on type of good)
9-a page dedicated for following up with tally/workers for each shift ,and the ships they have worked on i use a simple excel sheet for this
10-add feature to merge each new uploaded file to the database of files after clicking save.

New features yet to add:
11-make option in file manager to see full state of landing of ships .
12-fix genPVS to run correctly .
13-create loop and download templates .
14-in workforce tracking add option to generate a new day empty to fill with affecation and make dropdown or typing hints for usual things .
   add print to this tracking option
15-add map legende and map adding options for multiple goods with ease  

16-the dashboard should keep status of current ships on deck ,also it should have options to see ships on berth and expected
add to this port status emb/deb in day,week,month or year.





17-fix map position when changing from view to edit mode,
18-refactor the code for better working and even better organisation


#genDebarq.py excel should have this headings
from this "N° BL	,nombre colis	,Poids brute	,Client	produits" 
to this "N° BL	,Marchandise,	qte	,client	,poids	,type	,rec_qty"
(i will fix a standard version from the output of the sheet or should i make it selectable by columns on the gui interface )





---------------------------
i need to finish :
-add select checkbox to workforce manager
-add functionality to convert json to xlsx/csv table, when uploaded single file manager in statemanager 
-add feature to delete/rename columns in all tables 
-add copy/past feature to facilitate editing multiple cells.
-create tool for calculating surface ,in logistic tools,
-get started in making ui for handling template 