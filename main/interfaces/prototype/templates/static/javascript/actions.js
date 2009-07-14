function constructAPIURL(options) {
    
}


statusTemplate = new Ext.Toolbar.TextItem({
                text:'Loading',
                tooltip:'Loading.',
                id:'statusReplace'
            });
            
            
            
//Grid functions
//load the files for the selected queue item
function loadFiles(value, row, value3, value4){
    //row = gridView.getRow(row)
    //row.style.backgroundColor = 'yellow';
    //row.setAttribute("class", 'yellow-row'); //For Most Browsers
    ids = store.collect('nzo_id');
    currentFile = ids[row]
    url = 'tapi?mode=get_files&output=json&value='+currentFile
    storeFiles.proxy.conn.url = url;
    storeFiles.reload();
    //storeFiles.load(url)
}

//pushes changed values to sab and updates the grid
function updateGrid(grid){
    ids = store.collect('nzo_id');
    currentFile = ids[grid.row];
    var value = grid.value;
    var url;
    //script
    if (grid.field == "script"){
        url = "tapi?mode=change_script&value="+currentFile+"&value2="+value;
    }
    //unpack options
    else if (grid.field == "unpackopts"){
        var unp;
        if (grid.value == "" || !grid.value || grid.value == "None") { unp = 0}
        else if (grid.value == "Repair") {unp = 1}
        else if (grid.value == "Unpack") {unp = 2}
        else if (grid.value == "Delete") {unp = 3}
        url = "queue/change_opts?nzo_id="+currentFile+"&pp="+unp
    }
    else if (grid.field == "index")
    {
        var nzoid1 = ids[grid.originalValue];
        var nzoid2 = ids[value];
        url = "tapi?mode=switch&value="+nzoid1+"&value2="+nzoid2;
    }
    else if (grid.field == "cat")
    {
        url = "tapi?mode=change_cat&value="+currentFile+"&value2="+value
    }
    if (url){
        Ext.Ajax.request(
        {
           url: url,
           success: dummy,
           failure: dummy
        });
        store.reload();
    }
}

function deleteAll(){

    url = "tapi?mode=queue&name=delete&value=all"
    if (url){
        Ext.Ajax.request(
        {
           url: url,
           success: dummy,
           failure: dummy
        });
        store.reload();
        storeStatus.reload();
    }
};
   
function deleteAllHistory(){

    url = "tapi?mode=history&name=delete&value=all"
    if (url){
        Ext.Ajax.request(
        {
           url: url,
           success: dummy,
           failure: dummy
        });
        storeHistory.reload();
    }
};
   
function getGridSelected(Grid, remove)
{
    var ar = Grid.getSelectionModel().getSelections()
    var delids;
    for(i = 0; i < ar.length; i++){
        if (i==ar.length-1) comma = ''
        else comma = ','
        if (delids) delids = delids+ar[i].id+comma
        else delids = ar[i].id+comma
    }
    selectedNo = ar.length
    return delids
}

function s_returner(value)
{
    if (value == 1) return ''
    else return 's'
}

function removeSelected()
{
    ids = getGridSelected(queueGrid,true); 
    url = "tapi?mode=queue&name=delete&value="+ids
    Ext.Ajax.request({url: url});
    var msg = String.format('{0} item{1} deleted.', selectedNo, s_returner(selectedNo));
    Ext.example.msg('Deleted', msg);
    store.reload();
    storeStatus.reload();
}

function pauseSelected()
{
    ids = getGridSelected(queueGrid,false);
    url = "tapi?mode=queue&name=pause&value="+ids
    var msg = String.format('{0} item{1} paused.', selectedNo, s_returner(selectedNo));
    Ext.example.msg('Paused', msg);
    Ext.Ajax.request({url: url});
    store.reload();
    storeStatus.reload();

}

function resumeSelected()
{
    ids = getGridSelected(queueGrid,false);  
    url = "tapi?mode=queue&name=resume&value="+ids
    Ext.Ajax.request({url: url});
    var msg = String.format('{0} item{1} resumed.', selectedNo, s_returner(selectedNo));
    Ext.example.msg('Resumed', msg);
    store.reload();
    storeStatus.reload();

}

function prioritySelected(val, name)
{
    ids = getGridSelected(queueGrid,false);  
    url = "tapi?mode=queue&name=priority&value="+ids+"&value2="+val;
    Ext.Ajax.request({url: url});
    var msg = String.format('{0} item{1} set to {2} priority.', selectedNo, s_returner(selectedNo), name);
    Ext.example.msg('Priority', msg);
    store.reload();
}

function forcePrioritySelected()
{
    prioritySelected("2", "Force")
}    

function highPrioritySelected()
{
    prioritySelected("1", "High")
}

function normalPrioritySelected()
{
    prioritySelected("0", "Normal")
}

function lowPrioritySelected()
{
    prioritySelected("-1", "Low")
}

function removeSelectedHistory()
{
    ids = getGridSelected(historyGrid,true);
    if (ids){
        url = "tapi?mode=history&name=delete&value="+ids
        Ext.Ajax.request({url: url});
        var msg = String.format('{0} history job{1} deleted.', selectedNo, s_returner(selectedNo));
        Ext.example.msg('Deleted', msg);
        storeHistory.reload();
    }
}

//shutdown sabnzbd
function shutdownProgram(button)
{
    if (button == "yes")
    {
        Ext.MessageBox.show({
           msg: 'Closing SABnzbd, please wait...',
           progressText: 'Shutting down...',
           width:300,
           wait:true,
           waitConfig: {interval:200}
           //icon:'ext-mb-download', 
        });

        url = 'shutdown';
        Ext.Ajax.request(
        {
           url: url,
           success: shutdownComplete,
           failure: shutdownFailed
        });
    }
}


function shutdownComplete()
{
    Ext.MessageBox.hide();
    Ext.example.msg('Done', 'SABnzbd has been shut down!');
}

function shutdownFailed()
{
    Ext.MessageBox.hide();
    Ext.example.msg('Failed', 'Could not contact SABnzbd server, already shutdown?');
}

function changeColorScheme(color)
{
    url = 'tapi?mode=config&name=set_colorscheme&value='+color;
    Ext.Ajax.request(
    {
       url: url,
       success: dummy,
       failure: dummy
       
    });
}

function queueFinishAction(o , value){
    url = 'tapi?mode=queue&name=change_complete_action&value='+value;
    Ext.Ajax.request(
    {
       url: url,
       success: dummy,
       failure: dummy
       
    });
};

function limitSpeed(o , value){
    url = 'tapi?mode=config&name=set_speedlimit&value='+value;
    Ext.Ajax.request(
    {
       url: url,
       success: dummy,
       failure: dummy
       
    });
}