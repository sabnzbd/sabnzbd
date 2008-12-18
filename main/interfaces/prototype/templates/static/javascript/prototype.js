/*
Prototype Skin for SABnzbd 0.5.0 alpha 
created by switch
*/


/*
 * Ext JS Library 2.0.2
 * Copyright(c) 2006-2008, Ext JS, LLC.
 * licensing@extjs.com
 * 
 * http://extjs.com/license
 */


var store;
var storeFiles;
var autoreload = 10;
var currentFile;
var queueGrid;
var filesGrid;
var paused = false;
var statusTemplate;
var state2;
var southHeight;
var storeHistory;
var selectedNo; //used for keeping track of how many items were selected when an action was done
    
Ext.onReady(function(){

//-------------------------------------------------------------------------------------------------------------
//                                                       GRIDACTION
//-------------------------------------------------------------------------------------------------------------
        // vim: ts=4:sw=4:nu:fdc=2:nospell
        /**
        * RowAction plugin for Ext grid
        *
        * Contains renderer for an icon and fires events when icon is clicked
        *
        * @author    Ing. Jozef Sakalos <jsakalos at aariadne dot com>
        * @date      December 29, 2007
        * @version    Ext.ux.grid.RowAction.js 126 2008-01-31 03:33:50Z jozo 
        *
        * @license Ext.ux.grid.RowAction is licensed under the terms of
        * the Open Source LGPL 3.0 license.  Commercial use is permitted to the extent
        * that the code/component(s) do NOT become part of another Open Source or Commercially
        * licensed development library or toolkit without explicit permission.
        * 
        * License details: http://www.gnu.org/licenses/lgpl.html
        */

        Ext.ns('Ext.ux.grid');

        /**
        * @class Ext.ux.grid.RowAction
        * @extends Ext.util.Observable
        *
        * Creates new RowAction plugin
        * @constructor
        * @param {Object} config The config object
        *
        * @cfg {String} iconCls css class that defines background image
        */
        Ext.ux.grid.RowAction = function(config) {
        Ext.apply(this, config);

        this.addEvents({
            /**
             * @event beforeaction
             * Fires before action event. Return false to cancel the subsequent action event.
             * @param {Ext.grid.GridPanel} grid
             * @param {Ext.data.Record} record Record corresponding to row clicked
             * @param {Integer} rowIndex 
             */
             beforeaction:true
            /**
             * @event action
             * Fires when icon is clicked
             * @param {Ext.grid.GridPanel} grid
             * @param {Ext.data.Record} record Record corresponding to row clicked
             * @param {Integer} rowIndex 
             */
            ,action:true
        });

        Ext.ux.grid.RowAction.superclass.constructor.call(this);
        };

        Ext.extend(Ext.ux.grid.RowAction, Ext.util.Observable, {
         header:''
        ,sortable:false
        ,dataIndex:''
        ,width:20
        ,fixed:true
        ,lazyRender:true
        ,iconCls:''

        // private - plugin initialization
        ,init:function(grid) {
            this.grid = grid;
            var view = grid.getView();
            grid.on({
                render:{scope:this, fn:function() {
                    view.mainBody.on({
                        click:{scope:this, fn:this.onClick}
                    });
                }}
            });
            if(!this.renderer) {
                this.renderer = function(value, cell, record, row, col, store) {
                    cell.css += (cell.css ? ' ' : '') + 'ux-grid3-row-action-cell';
                    //very very bad work-around for changing resume/pause icon
                    var customClass = this.getIconCls(record, row, col);
                    if (customClass == "icon-pause" && record.data.status == "Paused") customClass = 'icon-play';
                    else if (customClass == "icon-play" && record.data.status != "Paused") customClass = 'icon-pause';
                    var retval = '<div class="' + customClass + '"';
                    retval += this.style ? ' style="' + this.style + '"' : '';
                    retval += this.qtip ? ' ext:qtip="' + this.qtip +'"' : '';
                    retval += '> </div>';
                    return retval;
                }.createDelegate(this);
            }
        } // eo function init

        // override for custom processing
        ,getIconCls:function(record, row, col) {
            return this.boundIndex ? record.get(this.boundIndex) : this.iconCls;
        } // eo function getIconCls
        
        // override for custom processing
        ,setIconCls:function(cls) {
            this.iconCls = cls;
        } // eo function getIconCls

        // private - icon click handler
        ,onClick:function(e, target) {
            var record, iconCls;
            var row = e.getTarget('.x-grid3-row');
            var col = this.grid.getView().getCellIndex(e.getTarget('.ux-grid3-row-action-cell'));

            if(false !== row && false !== col) {
                record = this.grid.store.getAt(row.rowIndex);
                iconCls = this.getIconCls(record, row.rowIndex, col);
                //very very bad work-around for changing resume/pause icon
                if (iconCls == 'icon-pause' && record.data.status == "Paused") iconCls = 'icon-play';              
                if(Ext.fly(target).hasClass(iconCls)) {
                    if(false !== this.fireEvent('beforeaction', this.grid, record, row.rowIndex)) {
                        this.fireEvent('action', this.grid, record, row.rowIndex, e);
                    }
                }
            }
        } // eo function onClick
        });

        // eof  
        
  
// Custom drag+drop by clarkke8  
	 
Ext.namespace('Ext.ux.dd');

Ext.ux.dd.GridReorderDropTarget = function(grid, config) {
    this.target = new Ext.dd.DropTarget(grid.getEl(), {
        ddGroup: grid.ddGroup || 'GridDD'
        ,grid: grid
        ,gridDropTarget: this
        ,notifyDrop: function(dd, e, data){
            // determine the row
            var t = Ext.lib.Event.getTarget(e);
            var rindex = this.grid.getView().findRowIndex(t);
            if (rindex === false) return false;
            if (rindex == data.rowIndex) return false;

            // fire the before move/copy event
            if (this.gridDropTarget.fireEvent(this.copy?'beforerowcopy':'beforerowmove', this.gridDropTarget, data.rowIndex, rindex, data.selections) === false) return false;

            // update the store
            var ds = this.grid.getStore();
            if (!this.copy) {
                for(i = 0; i < data.selections.length; i++) {
                    ds.remove(ds.getById(data.selections[i].id));
                }
            }
            ds.insert(rindex,data.selections);

            // re-select the row(s)
            var sm = this.grid.getSelectionModel();
            if (sm) sm.selectRecords(data.selections);

            // fire the after move/copy event
            this.gridDropTarget.fireEvent(this.copy?'afterrowcopy':'afterrowmove', this.gridDropTarget, data.rowIndex, rindex, data.selections);

            return true;
        }
        ,notifyOver: function(dd, e, data) {
            var t = Ext.lib.Event.getTarget(e);
            var rindex = this.grid.getView().findRowIndex(t);
            if (rindex == data.rowIndex) rindex = false;

            return (rindex === false)? this.dropNotAllowed : this.dropAllowed;
        }
    });
    if (config) {
        Ext.apply(this.target, config);
        if (config.listeners) Ext.apply(this,{listeners: config.listeners});
    }

    this.addEvents({
        "beforerowmove": true
        ,"afterrowmove": true
        ,"beforerowcopy": true
        ,"afterrowcopy": true
    });

    Ext.ux.dd.GridReorderDropTarget.superclass.constructor.call(this);
};

Ext.extend(Ext.ux.dd.GridReorderDropTarget, Ext.util.Observable, {
    getTarget: function() {
        return this.target;
    }
    ,getGrid: function() {
        return this.target.grid;
    }
    ,getCopy: function() {
        return this.target.copy?true:false;
    }
    ,setCopy: function(b) {
        this.target.copy = b?true:false;
    }
});


//row expander
Ext.grid.RowExpander = function(config){
    Ext.apply(this, config);

    this.addEvents({
        beforeexpand : true,
        expand: true,
        beforecollapse: true,
        collapse: true
    });

    Ext.grid.RowExpander.superclass.constructor.call(this);

    if(this.tpl){
        if(typeof this.tpl == 'string'){
            this.tpl = new Ext.Template(this.tpl);
        }
        this.tpl.compile();
    }

    this.state = {};
    this.bodyContent = {};
};

Ext.extend(Ext.grid.RowExpander, Ext.util.Observable, {
    header: "",
    width: 20,
    sortable: false,
    fixed:true,
    menuDisabled:true,
    dataIndex: '',
    id: 'expander',
    lazyRender : true,
    enableCaching: true,

    getRowClass : function(record, rowIndex, p, ds){
        p.cols = p.cols-1;
        var content = this.bodyContent[record.id];
        if(!content){
            content = this.getBodyContent(record, rowIndex);
        }
        if(content){
            p.body = content;
        }
        return this.state[record.id] ? 'x-grid3-row-expanded' : 'x-grid3-row-collapsed';
    },

    init : function(grid){
        this.grid = grid;

        var view = grid.getView();
        view.getRowClass = this.getRowClass.createDelegate(this);

        view.enableRowBody = true;

        grid.on('render', function(){
            view.mainBody.on('mousedown', this.onMouseDown, this);
        }, this);
    },

    getBodyContent : function(record, index){
        if(!this.enableCaching){
        //NOT USED
            var str = '';
            for (i=0;i<record.data.stages.length;i++)
            {               
                for (j=0;j<record.data.stages[i].actions.length;j++)
                {
                    str = str + record.data.stages[i].actions[j].name + ': ' + record.data.stages[i].actions[j].value + '<br /><br />'
                }
            }
            return str;
        }
        var content = this.bodyContent[record.id];
        if(!content){
            var str = '<p class="historyDetails">';
            for (i=0;i<record.data.stages.length;i++)
            {
            str = str + '<span class="historyDetail">' + record.data.stages[i].name + '</span><br />';
                for (j=0;j<record.data.stages[i].actions.length;j++)
                {
                    str = str + record.data.stages[i].actions[j].name + ': ' + record.data.stages[i].actions[j].value + '<br />'
                }
            str = str + '<br />';
            }
            str = str + '</span>';
            content = str;
        }
        return content;
    },

    onMouseDown : function(e, t){
        if(t.className == 'x-grid3-row-expander'){
            e.stopEvent();
            var row = e.getTarget('.x-grid3-row');
            this.toggleRow(row);
        }
    },

    renderer : function(v, p, record){
        p.cellAttr = 'rowspan="2"';
        return '<div class="x-grid3-row-expander">&#160;</div>';
    },

    beforeExpand : function(record, body, rowIndex){
        if(this.fireEvent('beforeexpand', this, record, body, rowIndex) !== false){
            if(this.tpl && this.lazyRender){
                body.innerHTML = this.getBodyContent(record, rowIndex);
            }
            return true;
        }else{
            return false;
        }
    },

    toggleRow : function(row){
        if(typeof row == 'number'){
            row = this.grid.view.getRow(row);
        }
        this[Ext.fly(row).hasClass('x-grid3-row-collapsed') ? 'expandRow' : 'collapseRow'](row);
    },

    expandRow : function(row){
        if(typeof row == 'number'){
            row = this.grid.view.getRow(row);
        }
        var record = this.grid.store.getAt(row.rowIndex);
        var body = Ext.DomQuery.selectNode('tr:nth(2) div.x-grid3-row-body', row);
        if(this.beforeExpand(record, body, row.rowIndex)){
            this.state[record.id] = true;
            Ext.fly(row).replaceClass('x-grid3-row-collapsed', 'x-grid3-row-expanded');
            this.fireEvent('expand', this, record, body, row.rowIndex);
        }
    },

    collapseRow : function(row){
        if(typeof row == 'number'){
            row = this.grid.view.getRow(row);
        }
        var record = this.grid.store.getAt(row.rowIndex);
        var body = Ext.fly(row).child('tr:nth(1) div.x-grid3-row-body', true);
        if(this.fireEvent('beforcollapse', this, record, body, row.rowIndex) !== false){
            this.state[record.id] = false;
            Ext.fly(row).replaceClass('x-grid3-row-expanded', 'x-grid3-row-collapsed');
            this.fireEvent('collapse', this, record, body, row.rowIndex);
        }
    }
});  
        
        
//-------------------------------------------------------------------------------------------------------------
//                                                          INIT
//-------------------------------------------------------------------------------------------------------------

    Ext.QuickTips.init();
    Ext.state.Manager.setProvider(new Ext.state.CookieProvider());
    
    
//-------------------------------------------------------------------------------------------------------------
//                                                              STORES
//-------------------------------------------------------------------------------------------------------------

    var queueItemXMLReader = new Ext.data.JsonReader({
            root: 'mainqueue.slotinfo',
            id: 'nzo_id'
        }, [
            {name: 'name', mapping: 'filename'},
            'mbleft', {name:'bytes', type: 'float'}, 'msgid', {name:'index', type: 'int'}, 
            {name:'unpackopts', convert: function(v){
            if (v == 0) {return "" }
            else if (v == 1) {return "Repair"}
            else if (v == 2) {return "Unpack"}
            else if (v == 3) {return "Delete"}
            } },
            'cat','script','status','percentage', 'nzo_id', 'avg_age', 'timeleft', 'priority', 'eta'
        ]);
        
    var statusXMLReader = new Ext.data.XmlReader({
            record: 'mainqueue',
            id: 'version'
        }, [
            {name: 'cache_limit', mapping: 'cache_limit'},
            'mbleft', 'mb', 'timeleft', 'kbpersec', 'eta', 'finishaction', 'status', 'paused', 'speedlimit'
        ]);
        
    var newQueueStatus = new Ext.data.HttpProxy({
                    url: 'tapi?mode=queue&output=json'
                })
                
    var newQueueStatus2 = new Ext.data.HttpProxy({
                    url: 'tapi?mode=queue&output=xml'
                })

//QueueStore
    //store = new Ext.data.GroupingStore({
    store = new Ext.data.GroupingStore({
        proxy: newQueueStatus,
        reader: queueItemXMLReader
        //,groupField:'priority'
        ,remoteSort:true
    });     
    //store.load({params:{start:0, limit:50}});
    store.on('load', function(rd, r, success) 
    {
        if (queueItemXMLReader.jsonData)
        {
            storeCats.loadData(queueItemXMLReader.jsonData);
            storeScripts.loadData(queueItemXMLReader.jsonData);
            storeQueueActions.loadData(queueItemXMLReader.jsonData);
        }
    });

    
//StatusStore
    storeStatus = new Ext.data.Store({
        proxy: newQueueStatus2,
        reader: statusXMLReader
    });
    storeStatus.load()

    storeStatus.on('load', function(rd, r, success) 
    {
        var tpl = new Ext.Template(
            ' Status: <span class="status_{status}">{status}</span> ','| Speed: {kbpersec}KB/s ','| Timeleft: {timeleft} '
        );
        //result = tpl.applyTemplate(r[0].data);
        //alert(result);
        if (statusTemplate){
            statEl = statusTemplate.getEl()
            if (r[0])
            {
                tpl.overwrite(statEl, r[0].data);
                if (r[0].data.paused == "True")
                {
                    queuePause.toggle(1)
                } else {
                    queuePause.toggle(0)
                }
            }
        }
        time = new Date();
        unixTime = time.getTime();
        graphlog = new Ext.data.Record()
        var graphlog = Ext.data.Record.create([
            {name: 'time'},
            {name: 'speed'}
        ]);
        
        if (r[0])
        {
    		speed = r[0].data.kbpersec;
    		paused = r[0].data.paused;
    		if (paused=="True") speed = 0;

    		if (paused=="True")
    		{
                document.title = "SABnzbd+ | Paused";
    						//alert("paused");
    		} else if 	(speed>0)
    		{
        		totalTimeRemain = r[0].data.timeleft;
                dltitle = "SABnzbd+ | "+totalTimeRemain+" | "+speed+"kB/s";
                document.title = dltitle;
    						//alert("down");
    		} else {
                document.title = "SABnzbd+ | Idle";
    						//alert("idle");
    		}
            speedlimit = r[0].data.speedlimit;
            speedbox.setValue(speedlimit);
            
        } else {
            speed = '0'
        }

        var graphlogRecord = new graphlog({
            time: unixTime,
            speed: speed
        });

        storeChart.add(graphlogRecord);
        drawChart();
    });
    storeStatus.load();

    
//HistoryStore
    storeHistory = new Ext.data.Store({
        url: 'tapi?mode=history&output=json',
        reader: new Ext.data.JsonReader({
            root: '',
            id: 'nzo'
        }, [
            {name: 'filename', mapping: 'filename'},
            'status', {name:'id', type: 'int', mapping: 'nzo'}, 'stages'
        ])
    });
    storeHistory.load({params:{start:0, limit:50}});
    
    var historyTemplate = new Ext.Template('{name}: {value}');
    
    var historyGridExpander = new Ext.grid.RowExpander({
        tpl : new Ext.Template(
            ''
        )
    });

    
//GraphLoggingStore 
    var storeChart = new Ext.data.SimpleStore({
        fields: [
           {name: 'time'},
           {name: 'speed', type: 'float'}
        ]
    });
//WarningsStore
    var storeWarnings = new Ext.data.Store({
        url: 'tapi?mode=warnings&output=json',
        reader: new Ext.data.JsonReader({
            root: 'warnings',
            id: 'id',
            totalRecords: '@total'
        }, [
            {name: 'name', mapping: 'name'}, {name:'id', type: 'int'}
        ])
    });
    storeWarnings.load();
    
//FilesStore
    storeFiles = new Ext.data.Store({
        url: 'tapi?mode=get_files&output=json&value=',
        reader: new Ext.data.JsonReader({
            record: 'slot',
            id: 'id',
            totalRecords: '@total'
        }, [
            {name: 'filename', mapping: 'filename'},
            'mbleft', {name:'bytes', type: 'float'}, {name:'id', type: 'int'}, 'age', 'status'
        ])
    });

    //storeFiles.on('beforeload', function(){state2 = filesGrid.getView().getScrollState();})
    //storeFiles.on('load', function(){filesGrid.getView().restoreScroll(state2);})
    /*storeFiles.on('beforeload', function(){
        state2 = (grid.rendered)
            ? filesGrid.view.scroller.dom.scrollTop
            : 0;
    });
    storeFiles.on('load', function(){
        filesGrid.view.scroller.scroll('down', state2, true);
    });  */
        


    
//ScriptsStore
    var storeScripts = new Ext.data.Store({
        url: 'tapi?mode=queue&output=json',
        reader: new Ext.data.JsonReader({
            root: 'mainqueue.script_list.scripts',
            //id: 'id',
            totalRecords: '@total'
        }, [
            {name: 'script', mapping: 'name'}
        ])
    });
    //storeScripts.load();
    store.load({params:{start:0, limit:50}});
    
    var queueActions = [{
        script: 'one'
    }, {
        script: 'two'
    }];
    
var TopicRecord = Ext.data.Record.create([
    {name: 'script', mapping: 'script'}
]);

var myNewRecord = new TopicRecord({
    script: 'one'
});

    
    var storeQueueActions = new Ext.data.Store({
        url: 'tapi?mode=queue&output=json',
        reader: new Ext.data.JsonReader({
            root: 'mainqueue.script_list.scripts',
            //id: 'id',
            totalRecords: '@total'
        }, [
            {name: 'script', mapping: 'name'}
        ])
    });
    //storeQueueActions.load();
    //storeQueueActions.add(myNewRecord);
    
    
    
    var storeCats = new Ext.data.Store({
        url: 'tapi?mode=queue&output=json',
        reader: new Ext.data.JsonReader({
            root: 'mainqueue.cat_list.categories',
            //id: 'id',
            totalRecords: '@total'
        }, [
            {name: 'category', mapping: 'name'}
        ])
    });
    //storeCats.load();
    
    
var unpackStrings = [
    ['None'],
    ['Repair'],
    ['Unpack'],
    ['Delete']
]
    
//UnpackStore
var storeUnpack = new Ext.data.SimpleStore({
    fields: [
       {name: 'unpackopts'}
    ]
});
storeUnpack.loadData(unpackStrings);


//-------------------------------------------------------------------------------------------------------------
//                                                              ACTIONS
//-------------------------------------------------------------------------------------------------------------

//CUSTOM FORMATTERS

    //percentage bar formatter
    var progressvar = function(val){
        if (val > 0){
            return '<div id="progressBar"><div id="percentage" style="width: '+val+'%;   position: relative;   background-color: #9bf;   height: 100%;font-size:9px;padding:1px;text-align:center;">'+val+'%</div></div>';
        }
            else { return
        }
    }

    //status formatter
    var statusChange = function (val)
    {
        if(val == "finished")
        {
            return '<span style="color:red;">' + val + '</span>';
        }else if(val == "active")
        {
            return '<span style="color:green;">' + val + '</span>';
        }else if(val == "queued")
        {
            return '<span style="color:yellow;">' + val + '</span>';
        }
        return val;
    }       
    
    //failed/completed/inprogress indicator for history
    function historyStatus(value)
    {
        if (value=="Completed")
        {
            return '<center><img src="./static/shared/icons/fam/bullet_green.png" /></center>'
        } else if (value == "Failed")
        {
            return '<center><img src="./static/shared/icons/fam/bullet_red.png" /></center>'
        } else {
            return '<center><img src="./static/shared/icons/fam/bullet_yellow.png" /></center>'
        }
    }

    //truncate a string to x characters (depreciated)
    function truncateString(value){
        if (value.length > 35){
            string = value.slice(0,33);
            string = string+'...';
            return string
        } else {
            return value
        }
    }
    
    //file size formatter
    function fileSizes1(value){
        kb = value / 1024
        if (kb > 1024){
            mb = kb / 1024
            if (mb > 1024){
                gb = mb/1024
                return gb.toFixed(2)+"GB"
            } else 
            {
                return mb.toFixed(2)+"MB"
            }
        } else {
            return kb.toFixed(2)+"KB"
        }
    } 

    //file size formatter
    function fileSizes(value){
        kb = value / 1024
        mb = value / 1048576
        gb = value / 1073741824
        if (gb >= 1){
            return gb.toFixed(2)+"GB"
        } else if (mb >= 1) {
            return mb.toFixed(2)+"MB"
        } else {
            return kb.toFixed(2)+"KB"
        }
    }

        //color the background cells of the priority
        function priorityRenderer(val, meta)
        {
            if(val == "High")
            {
                //alert('hey')
                //meta.attr='style="background-color:#dafad9;"'; //green
                meta.css += ' priority-cell-high'; 
            }else if(val == "Low")
            {
                //meta.attr='style="background-color:#fad9d9;"'; //red
                meta.css += ' priority-cell-low';
            }
            return val;
        }
        
        //color the background cells of the status
        function statusRender(val, meta)
        {
            if(val == "Downloading")
            {
                //alert('hey')
                meta.attr='style="background-color:#b1e698;"'; //green
            }else if(val == "Paused")
            {
                meta.attr='style="background-color:#e7e7e7;"'; //grey
            }
            return val;
        }
    
    //Delete button in queue
    var delqueue = new Ext.ux.grid.RowAction(
    //{iconCls:'icon-pause',qtip:'Pause'},
    {iconCls:'icon-cross',qtip:'Delete'}
    );
    
    delqueue.on('action', function(something, grid, record) 
    {
        ids = store.collect('nzo_id');
        currentFile = ids[record];
        url = 'tapi?mode=queue&name=delete';
        Ext.Ajax.request(
        {
           url: url,
           success: dummy,
           failure: dummy,
           params: {value: currentFile}
        });
        store.reload()
    });  
    
    var pauqueue = new Ext.ux.grid.RowAction(
    {iconCls:'icon-pause',qtip:'Pause'}
    //{iconCls:'icon-cross',qtip:'Delete'}
    );
    
    pauqueue.on('action', function(something, grid, record) 
    {
        status = grid.data.status;
        //var pauicon = pauqueue.getIconCls()
        //if (pauicon == "icon-pause") pauqueue.setIconCls('icon-play')
        currentFile = grid.data.nzo_id;
        url = 'tapi?mode=queue&name=pause';
        if (status == 'Paused') url = 'tapi?mode=queue&name=resume';
        
        Ext.Ajax.request(
        {
           url: url,
           success: dummy,
           failure: dummy,
           params: {value: currentFile}
        });
        store.reload()
    });  
    
 

        //Delete button in history
    var delhistory = new Ext.ux.grid.RowAction({iconCls:'icon-cross',qtip:'Delete'});
    
    delhistory.on('action', function(something, grid, record) 
    {
        ids = storeHistory.collect('id');
        currentFile = ids[record];
        url = 'history/delete?job='+currentFile;
        Ext.Ajax.request(
        {
           url: url,
           success: dummy,
           failure: dummy
        });
        storeHistory.reload()
    });  

    //expand a combo box
    function openCombo(combo){combo.expand()}
       
    //blank handler - used as a placeholder   
    function dummy(){} 

    //queue pause on/off
    function pausetoggle(item, pressed)
    {
        if (paused)
        {
            url = 'tapi?mode=resume';
            paused = false;
        } else 
        {
            url = 'tapi?mode=pause';
            paused = true;
        }
        
        Ext.Ajax.request(
        {
           url: url,
           success: dummy,
           failure: dummy
        })
        storeStatus.reload();
        Ext.example.msg('Queue Paused', 'Pause was set to {0}.',  pressed);
    }
   
//MESSAGE BOX FUNCTION
    Ext.example = function()
    {
    var msgCt;

    function createBox(t, s){
        return ['<div class="msg">',
                '<div class="x-box-tl"><div class="x-box-tr"><div class="x-box-tc"></div></div></div>',
                '<div class="x-box-ml"><div class="x-box-mr"><div class="x-box-mc"><h3>', t, '</h3>', s, '</div></div></div>',
                '<div class="x-box-bl"><div class="x-box-br"><div class="x-box-bc"></div></div></div>',
                '</div>'].join('');
    }
    return {
        msg : function(title, format){
            if(!msgCt){
                msgCt = Ext.DomHelper.insertFirst(document.body, {id:'msg-div'}, true);
            }
            msgCt.alignTo(document, 't-t');
            var s = String.format.apply(String, Array.prototype.slice.call(arguments, 1));
            var m = Ext.DomHelper.append(msgCt, {html:createBox(title, s)}, true);
            m.slideIn('t').pause(1).ghost("t", {remove:true});
        },

        init : function(){
            var t = Ext.get('exttheme');
            if(!t){ // run locally?
                return;
            }
            var theme = Cookies.get('exttheme') || 'aero';
            if(theme){
                t.dom.value = theme;
                Ext.getBody().addClass('x-'+theme);
            }
            t.on('change', function(){
                Cookies.set('exttheme', t.getValue());
                setTimeout(function(){
                    window.location.reload();
                }, 250);
            });

            var lb = Ext.get('lib-bar');
            if(lb){
                lb.show();
            }
        }
    };
    }();

   
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
    
    function highPrioritySelected()
    {
        ids = getGridSelected(queueGrid,false);
        url = "tapi?mode=queue&name=priority&value="+ids+"&value2=1";
        Ext.Ajax.request({url: url});
        var msg = String.format('{0} item{1} set to high priority.', selectedNo, s_returner(selectedNo));
        Ext.example.msg('Priority', msg);
        store.reload();

    }
    
    function normalPrioritySelected()
    {
        ids = getGridSelected(queueGrid,false);  
        url = "tapi?mode=queue&name=priority&value="+ids+"&value2=0";
        Ext.Ajax.request({url: url});
        var msg = String.format('{0} item{1} set to normal priority.', selectedNo, s_returner(selectedNo));
        Ext.example.msg('Priority', msg);
        store.reload();

    }
    
    function lowPrioritySelected()
    {
        ids = getGridSelected(queueGrid,false);  
        url = "tapi?mode=queue&name=priority&value="+ids+"&value2=-1";
        Ext.Ajax.request({url: url});
        var msg = String.format('{0} item{1} set to low priority.', selectedNo, s_returner(selectedNo));
        Ext.example.msg('Priority', msg);
        store.reload();

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

//-------------------------------------------------------------------------------------------------------------
//                                                              TABS
//-------------------------------------------------------------------------------------------------------------

    var filesGridView = new Ext.grid.GridView({ 
       //from http://extjs.com/learn/Ext_FAQ#Maintain_GridPanel_scroll_position_across_Store_reloads
       //with modifications by keckeroo http://extjs.com/forum/showthread.php?p=165216#post165216
        onLoad: Ext.emptyFn,
        autoFill: true,
        forceFit: true,
        listeners: {
            beforerefresh: function(v) {
               v.scrollTop = v.scroller.dom.scrollTop;
               v.scrollHeight = v.scroller.dom.scrollHeight;
            },
            refresh: function(v) {
               v.scroller.dom.scrollTop = v.scrollTop + (v.scrollTop == 0 ? 0 : v.scroller.dom.scrollHeight - v.scrollHeight);
            }
        }
    });  //end historyGridView 



    filesGrid = new Ext.grid.GridPanel(
            {
                store: storeFiles,
                title: 'File Info',
                id: 'filesgrid',
                view: filesGridView,
                columns: [{
                        header: "ID",
                        id: "filesid",
                        width: 70,
                        sortable: true,
                        dataIndex: 'id'
                    },{
                        header: "Filename",
                        id: "filesFilename",
                        width: 370,
                        sortable: true,
                        dataIndex: 'filename'
                    },{
                        header: "Size",
                        width: 80,
                        sortable: true,
                        dataIndex: 'bytes',
                        renderer: Ext.util.Format.fileSize
                    },{
                        header: "Age",
                        width: 80,
                        sortable: true,
                        dataIndex: 'age'
                    },{
                        header: "Status",
                        width: 80,
                        sortable: true,
                        dataIndex: 'status',
                        renderer: statusChange
                    }],
                width: 600,
                height: 250,
                viewConfig: {
                    forceFit: true
                },
                //autoHeight:true,
                //autoExpandColumn:'Filename',
                autoFitColumns: true,
                iconCls: 'icon-fileinfo',
                enableDragDrop:true
            });
            
    var historyGrid2 = new Ext.grid.GridPanel(
    {
        store: storeHistory,
        title: 'History',
        id: 'hgrid',
            columns: [{
                header: "Job",
                id: "historyid",
                width: 35,
                sortable: true,
                dataIndex: 'id'
            },{
                header: "Filename",
                id: "historyFilename",
                width: 170,
                sortable: true,
                dataIndex: 'filename'
            },{
                header: "Status",
                width: 40,
                sortable: true,
                dataIndex: 'status',
                renderer: historyStatus
            },
            delhistory],
            plugins:[delhistory],
            viewConfig: {
                forceFit: true
            },
            /*bbar:[
            historyToolbar
            ],           */
                width: 600,
                height: 250,
                viewConfig: {
                    forceFit: true
                },
                //autoHeight:true,
                autoScroll:true,
                //autoExpandColumn:'Filename',
                autoFitColumns: true,
                iconCls: 'icon-fileinfo',
                enableDragDrop:false
    });

            
    //TAB - South Tabs
    chartGridDebug = new Ext.grid.GridPanel(
            {
                store: storeChart,
                title: 'Chart Debug',
                id: 'chartgrid',
                columns: [{
                    header: "time",
                    id: "time",
                    width: 70,
                    sortable: true,
                    dataIndex: 'time'
                },{
                    header: "speed",
                    id: "chartSpeed",
                    width: 370,
                    sortable: true,
                    dataIndex: 'speed'
                }],
                viewConfig: {
                    forceFit: true
                },
                width: 600,
                height: 250,
                //autoHeight:true,
                //autoExpandColumn:'Filename',
                autoFitColumns: true,
                iconCls: 'icon-fileinfo',
                enableDragDrop:true
            });
            
            
    //chart tab
    function drawChart() {
        cPanel = document.getElementById("chartContainer");
        
        activeId = southTabs.getActiveTab().id;
        if (cPanel && activeId == "chartContainer"){
            //var chartInfo = getData(store, 'name', column);
            total = storeChart.getCount();
            data = storeChart.getRange(0, total);
            if (total > 0)
            {
                //alert(data.length);
                var d = Array();
                for(i=0;i<total;i++)
                {
                    //format it into a format flot likes
                    d.push([data[i].data.time, data[i].data.speed]);
                    //alert(data[i].data.time);
                }
                //alert(d[0]);
                


                    height = southHeight - 30;
                    cPanel.style.height = height+"px";
                    var options = {
                        xaxis: { mode: "time" }
                        , colors: ["red", "#d18b2c", "#dba255", "#919733"]
                    };
                    $.plot($("#chartContainer"), [d], options);

                
            }
        }
    }
    
    function resizeBottom()
    {
        aPanel = document.getElementById("filesgrid");
        bPanel = document.getElementById("warningsContainer");
        cPanel = document.getElementById("chartContainer");
        
        height = southHeight - 30;
        
        if (aPanel) {
            aPanel.style.height = height+"px";
            filesGrid.setHeight(height)
        }
        if (bPanel) {
            bPanel.style.height = height+"px";
            //filesGrid.setHeight(height)
        }
        if (cPanel) cPanel.style.height = height+"px";
    }
    
    var commonChartStyle = {"height": "10px"};
    var southTabs =  new Ext.TabPanel(
    {
        border:false,
        id: 'southTabs',
        /*
        viewConfig: {
                    forceFit: true
                },
                */
        autoHeight: true,
                viewConfig: {
                    forceFit: true
                },
        activeTab:1,
        listeners: {
                tabchange: function() {
                                drawChart();
                                resizeBottom();
                            }
            },
        tabPosition:'bottom',
        items:[
            {
                title: 'Graph',
                style: commonChartStyle,
                id: 'chartContainer',
                width: 600,
                height: 250,
                iconCls: 'icon-chart',
                viewConfig: {
                    forceFit: true
                },
                handler: function() {drawChart();}
            },
            
            filesGrid,
            //historyGrid2,
            new Ext.grid.GridPanel(
            {
                id: 'warningsContainer',
                store: storeWarnings,
                title: 'Error Log',
                columns: [{
                    header: "ID",
                    id: "id",
                    width: 10,
                    sortable: true,
                    dataIndex: 'id'
                },{
                    header: "Error",
                    width: 370,
                    sortable: true,
                    dataIndex: 'name'
                }],
                viewConfig: {
                    forceFit: true
                },
                width: 600,
                height: 250,
                //autoHeight:true,
                //autoExpandColumn:'Filename',
                autoFitColumns: true,
                iconCls: 'icon-fileinfo'
        })]
    });
                    
                    
                    
    //FORM - Adding nzb                
    var nzbtabs = new Ext.TabPanel(
    {
            xtype:'tabpanel',
            activeTab: 0,
            defaults:{autoHeight:true, bodyStyle:'padding:10px'},
            items:[{
                xtype:'form',
                title:'Add by Newzbin ID',
                layout:'form',
                defaultType: 'textfield',
                buttons: [{
                                text: 'Add'
                }],
                items: [{
                    fieldLabel: 'Newzbin ID',
                    name: 'nzb_id',
                    emptyText:'Enter a newzbin id...',
                    value: ''
                }, new Ext.form.ComboBox({
                    fieldLabel: 'Action',
                    store: storeUnpack,
                    displayField:'unpackopts',
                    typeAhead: true,
                    triggerAction: 'all',
                    emptyText:'Select an action...',
                    mode: 'local',
                    selectOnFocus:true
                }), new Ext.form.ComboBox({
                    fieldLabel: 'Script',
                    store: storeScripts,
                    displayField:'script',
                    typeAhead: true,
                    triggerAction: 'all',
                    emptyText:'Select a script...',
                    selectOnFocus:true
                }), new Ext.form.ComboBox({
                    fieldLabel: 'Category',
                    store: storeCats,
                    displayField:'category',
                    typeAhead: true,
                    triggerAction: 'all',
                    emptyText:'Select a category...',
                    selectOnFocus:true
                })]
            },{
                xtype:'form',
                title:'Add by URL',
                layout:'form',
                defaults: {autoHeight:true,autoWidth:true},
                defaultType: 'textfield',
                items: [{
                    fieldLabel: 'URL',
                    name: 'nzb_id',
                    emptyText:'Enter a newzbin id...',
                    value: ''
                }, new Ext.form.ComboBox({
                    fieldLabel: 'Action',
                    store: storeUnpack,
                    displayField:'unpackopts',
                    typeAhead: true,
                    triggerAction: 'all',
                    emptyText:'Select an action...',
                    mode: 'local',
                    selectOnFocus:true
                }), new Ext.form.ComboBox({
                    fieldLabel: 'Script',
                    store: storeScripts,
                    displayField:'script',
                    typeAhead: true,
                    triggerAction: 'all',
                    emptyText:'Select a script...',
                    selectOnFocus:true
                }), new Ext.form.ComboBox({
                    fieldLabel: 'Category',
                    store: storeCats,
                    displayField:'category',
                    typeAhead: true,
                    triggerAction: 'all',
                    emptyText:'Select a category...',
                    selectOnFocus:true
                })]
            },{
                xtype:'form',
                title:'Add local file',
                layout:'form',
                defaults: {autoHeight:true,autoWidth:true},
                defaultType: 'textfield',
                items: [{
                    fieldLabel: 'Local File',
                    name: 'nzb_id',
                    emptyText:'Enter a newzbin id...',
                    value: ''
                }, new Ext.form.ComboBox({
                    fieldLabel: 'Action',
                    store: storeUnpack,
                    displayField:'unpackopts',
                    typeAhead: true,
                    triggerAction: 'all',
                    emptyText:'Select an action...',
                    mode: 'local',
                    selectOnFocus:true
                }), new Ext.form.ComboBox({
                    fieldLabel: 'Script',
                    store: storeScripts,
                    displayField:'script',
                    typeAhead: true,
                    triggerAction: 'all',
                    emptyText:'Select a script...',
                    selectOnFocus:true
                }), new Ext.form.ComboBox({
                    fieldLabel: 'Category',
                    store: storeCats,
                    displayField:'category',
                    typeAhead: true,
                    triggerAction: 'all',
                    emptyText:'Select a category...',
                    selectOnFocus:true
                })]
            }]

    });

    var nzbform = new Ext.TabPanel({
    xtype:'tabpanel',
    activeTab: 0,
    items: [{
        title:'Add by Newzbin ID/ URL',
		contentEl: 'AddNZB1'

    },{
        title:'Add by file',
		contentEl: 'AddNZB2'

    }]
	});
    
/*
   var settingsTabs =  new Ext.TabPanel(
    {
        region: 'center',
        border:false,
        enableTabScroll:true,
        activeTab:0,
        tabPosition:'top',
        layoutOnTabChange:true,
        items:[
        {
            
            title: 'Downloads',
            iconCls: 'icon-chart',
            border:false,
            autoScroll:true,
            layout:'fit',
            items:new Ext.TabPanel(
            {
                region: 'center',
                hideBorders:true,
                activeTab:0,
                tabPosition:'top',
                items:[{
                    title: 'General',
                    border:false,
                    region: 'center',
                    xtype:'form',
                    layout: 'form',
                    defaults:{autoScroll:true},
                    margins:'30 30 30 30', 
                    labelWidth:130,
                    items:[new Ext.form.FieldSet(
                    {
                        title: 'Download Folders',
                        autoHeight: true,
                        collapsible:true,
                        defaultType: 'textfield',
                        items: [
                        {
                                fieldLabel: 'Incomplete Folder',
                                name: 'first',
                                width:250
                            }, {
                                fieldLabel: 'Complete Folder',
                                name: 'last',
                                width:250
                        }] 
                    }),new Ext.form.FieldSet({
                        title: 'Speed Limiting',
                        autoHeight: true,
                        collapsible:true,
                        defaultType: 'textfield',
                        items: [{
                                fieldLabel: 'Download Speed Limit (KB/s)',
                                name: 'first',
                                width:50
                            }
                        ]
                    })]
                },{
                    title: 'Categories'
                }]
            })
        },{
            title: 'Web Server',
            layout:'fit',
            autoScroll:true,
            items:
                new Ext.form.FieldSet({
                    autoHeight: true,
                    region: 'center',
                    border:false,
                    collapsible:true,
                    defaultType: 'textfield',
                    items: [{
                            fieldLabel: 'Host',
                            name: 'fhgfh',
                            width:150
                        },{
                            fieldLabel: 'Port',
                            name: 'hgfhgf',
                            width:50
                        },{
                            fieldLabel: 'Web Username',
                            name: 'first',
                            width:100
                        },{
                            fieldLabel: 'Web Password',
                            name: 'first',
                            width:100
                        },new Ext.form.ComboBox({
                        fieldLabel: 'Primary Skin',
                        store: storeCats,
                        displayField:'category',
                        typeAhead: true,
                        triggerAction: 'all',
                        emptyText:'Select a category...',
                        selectOnFocus:true
                    }),new Ext.form.ComboBox({
                        fieldLabel: 'Color Schema',
                        store: storeCats,
                        displayField:'category',
                        typeAhead: true,
                        triggerAction: 'all',
                        emptyText:'Select a category...',
                        selectOnFocus:true
                    }),new Ext.form.ComboBox({
                        fieldLabel: 'Secondary Skin',
                        store: storeCats,
                        displayField:'category',
                        typeAhead: true,
                        triggerAction: 'all',
                        emptyText:'Select a category...',
                        selectOnFocus:true
                    })
                    ]
            })

        },{
            
            title: 'Post-Processing',
            autoScroll:true,
            layout:'fit',
            items:new Ext.TabPanel(
            {
                region: 'center',
                border:false,
                activeTab:0,
                tabPosition:'top',
                items:[{
                    title: 'General',
                    region: 'center',
                    layout: 'fit',
                    defaults:{autoScroll:true},
                    items:
                        new Ext.form.FieldSet({
                            title: 'Switches',
                            collapsible:true,
                            labelWidth:190,
                            autoHeight: true,
                            defaultType: 'textfield',
                            items: [{
                                    fieldLabel: 'Enable Unrar',
                                    name: 'unrar',
                                    xtype:'checkbox',
                                    checked:true
                                },{
                                    fieldLabel: 'Enable Unzip',
                                    name: 'unzip',
                                    xtype:'checkbox',
                                    checked:true
                                },{
                                    fieldLabel: 'Enable .001 Joining',
                                    name: 'filejoin',
                                    xtype:'checkbox',
                                    checked:true
                                },{
                                    fieldLabel: 'Enable .TS Joining',
                                    name: 'tsjoin',
                                    xtype:'checkbox',
                                    checked:true
                                },{
                                    fieldLabel: 'Enable .PAR Cleanup',
                                    name: 'par_cleanup',
                                    xtype:'checkbox',
                                    checked:true
                                },{
                                    fieldLabel: 'Safe Post-Process',
                                    name: 'safe_postproc',
                                    xtype:'checkbox',
                                    checked:true
                                }
                            ]
                        })
                },{
                        title: 'Categories'
                }]
            })
        },{
            title: 'Servers'
        },{
            title: 'Newzbin'
        },{
            title: 'Scheduling'
        }]
    });        
    */
	
	
    // what is this for???
    var tabs = new Ext.TabPanel(
    {
        region: 'center',
        margins:'3 3 3 0', 
        activeTab: 0,
        defaults:{autoScroll:true},
        items:[{
            title: 'Bogus Tab',
            html: Ext.example.bogusMarkup
        },{
            title: 'Another Tab',
            html: Ext.example.bogusMarkup
        },{
            title: 'Closable Tab',
            html: Ext.example.bogusMarkup,
            closable:true
        }]
    });

    
    
    function getData(store, nameColumn, dataColumn) {
        var dataResults = new Array();
        var tickResults = new Array();
        for( var recordIndex = 0; recordIndex < store.getCount(); recordIndex++ ) {
            var record = store.getAt(recordIndex);
            var tmpData = [(recordIndex+1)*2, record.get(dataColumn)];
            var series = {
                bars: { show: true },
                label: record.get(nameColumn),
                data: [ tmpData, tmpData ], // workaround
                color: recordIndex
            }
            dataResults.push( series );
            tickResults.push([ ((recordIndex+1)*2)+1, record.get(nameColumn) ]);
        }
        return {
            data:dataResults,
            ticks:tickResults
        };
    }


        
    
    
    
    
//-------------------------------------------------------------------------------------------------------------
//                                                     WINDOWS/PANELS
//-------------------------------------------------------------------------------------------------------------

    //WINDOW - Adding nzb
    var nzbWindow = new Ext.Window({
        title: 'Add .nzb file',
        width: 340,
        height:300,
        minWidth: 350,
        minHeight: 250,
        bodyBorder:false,
        border:false,
        shadow: true,
        layout: 'fit',
        plain:true,
        bodyStyle:'padding:5px;',
        buttonAlign:'center',
        closeAction:'hide',
        items: nzbform
    });


    
    // PANEL - center viewport
    var settingsMain = new Ext.Panel(
    {
        title: 'General',
        region: 'center',
        margins:'3 3 3 0', 
        layout: 'fit',
        defaults:{autoScroll:true},
        frame:true,
        items:[new Ext.form.FieldSet(
        {
            title: 'Download Folders',
            autoHeight: true,
            layout: 'fit',
            defaultType: 'textfield',
            items: [{
                    fieldLabel: 'Incomplete Folder',
                    name: 'first',
                    width:290
                }, {
                    fieldLabel: 'Complete Folder',
                    name: 'last',
                    width:290
                }
                ]
        }),new Ext.form.FieldSet({
            title: 'Speed Limiting',
            autoHeight: true,
            defaultType: 'textfield',
            checkboxToggle:false,
            items: [{
                    fieldLabel: 'Download Speed Limit (KB/s)',
                    name: 'first',
                    width:50
                }
            ]
        }),
            new Ext.form.FieldSet({
                title: 'Web Server',
                autoHeight: true,
                defaultType: 'textfield',
                items: [
                {
                    fieldLabel: 'Host',
                    name: 'fhgfh',
                    width:50
                },{
                    fieldLabel: 'Port',
                    name: 'hgfhgf',
                    width:50
                },{
                    fieldLabel: 'Web Username',
                    name: 'first',
                    width:50
                },{
                    fieldLabel: 'Web Password',
                    name: 'first',
                    width:50
                },new Ext.form.ComboBox({
                    fieldLabel: 'Primary Skin',
                    store: storeCats,
                    displayField:'category',
                    typeAhead: true,
                    triggerAction: 'all',
                    emptyText:'Select a category...',
                    selectOnFocus:true
                }),new Ext.form.ComboBox({
                    fieldLabel: 'Color Schema',
                    store: storeCats,
                    displayField:'category',
                    typeAhead: true,
                    triggerAction: 'all',
                    emptyText:'Select a category...',
                    selectOnFocus:true
                }),new Ext.form.ComboBox({
                    fieldLabel: 'Secondary Skin',
                    store: storeCats,
                    displayField:'category',
                    typeAhead: true,
                    triggerAction: 'all',
                    emptyText:'Select a category...',
                    selectOnFocus:true
                })
                ]
            })]
    });

    // PANEL - west viewport
    var nav = new Ext.Panel({
        title: 'Navigation',
        header:false,
        region: 'west',
        split: true,
        width: 200,
        collapsible: false,
        margins:'3 0 3 3',
        cmargins:'3 3 3 3',
        frame:true
    });
    
    var navm = new Ext.tree.TreePanel({
        title: 'Navigation',
        region: 'west',
        header:false,
        useArrows:true,
        autoScroll:true,
        width: 200,
        split: true,
        containerScroll: true, 
        frame:true
    });

	
	var settingsTree = new Ext.tree.TreePanel({
		id: 'settings-tree',
		animate:true, 
		autoScroll:true,
		autoHeight: true,
		loader: new Ext.tree.TreeLoader({dataUrl:'config'}),
		bodyStyle: 'background-color:#e8e8e8;',
		enableDD:false,
		containerScroll: false,
		useArrows: true,
        region:'west',
		border:false,
        split: true,
        width: 200,
		collapsible: false,
		collapsed: false
	});
	
	function loadConfig(response,z)
	{
		//settingsPanel.
		//alert("ok");
		Ext.getDom('settings-panel').innerHTML = response.responseText;
		//Ext.getDom('settings-panel').innerHTML = "hi";
	}
	
	function fetchConfig(page)
	{
		url = 'config/'+page+'/';
		Ext.Ajax.request(
		{
		   url: url,
		   success: loadConfig,
		   failure: dummy
		});
	}
	
	settingsTree.on('click', function(n){
    	var sn = this.selModel.selNode || {}; // selNode is null on initial selection
    	if(n.leaf && n.id != sn.id){  // ignore clicks on folders and currently selected node 
    		//alert(n.text);
			switch(n.text)
			{
				case "Web Server": 
					fetchConfig("general"); 
					break;
				case "Post-Processing": 
					fetchConfig("switches"); 
					break;
				case "Newzbin": 
					fetchConfig("newzbin"); 
					break;
				case "Scheduling": 
					fetchConfig("scheduling"); 
					break;
				case "Folders": 
					fetchConfig("directories"); 
					break;
				case "Categories": 
					fetchConfig("categories"); 
					break;
				case "RSS": 
					fetchConfig("rss"); 
					break;
				case "Email": 
					fetchConfig("email"); 
					break;
				case "Add New": 
					fetchConfig("server"); 
					break;
			}
    	}
    });
	
	


	var settingsTreeRoot = new Ext.tree.AsyncTreeNode({
		text: 'Settings', 
		draggable:false, // disable root node dragging
		expanded: true,
		id:'source'
	});
	settingsTree.setRootNode(settingsTreeRoot);

	var settingsPanel = {
		id: 'settings-panel',
        title: 'Settings',
        region: 'center',
        bodyStyle: 'padding-left:150px;background:#eee;',
		cls: 'autoScroll',
		html: '<p class="details-info">This is only a working settings page, the full redesign has not been done yet.</p>'
    };


	var settingsViewport = {
			id: 'settings-view',
			layout: 'border',
			title: 'Ext Layout Browser',
			items: [settingsTree,
				settingsPanel
			]
	        
	    };
		
	

	
    //WINDOW - Settings
    var winSettings = new Ext.Window({
        title: 'Settings',
		id: 'settings-window',
        closable:true,
        width:1024,
        height:600,
		autoScroll: true,
        //border:false,
        plain:true,
        layout: 'border',
        closeAction:'hide',
        constrain:true,
        maximizable:true,
        items: [settingsTree,
				settingsPanel
			]
        /*,
        buttons:[
        {text: 'Save'},
        {text: 'Cancel'}]*/
    });
    /*items: [nav, settingsMain],
        width:800,
        height:450,
*/
    
//-------------------------------------------------------------------------------------------------------------
//                                                              TOOLBARS
//-------------------------------------------------------------------------------------------------------------
    
    sabMenu = new Ext.menu.Menu({
        items:[
            {
                text:'Add-NZB',
                tooltip:'Add an nzb file to the queue',
                iconCls:'add',
                handler: function()
                {
                nzbWindow.show();
                }
            },            
            {
                text:'Settings',
                tooltip:'Edit the configuration settings of SABnzbd',
                iconCls:'settings',
                handler: function()
                {
                    winSettings.show();
                    winSettings.maximize();
                }
            },
            {
                text:'Choose Theme',
                tooltip:'Choose the current theme for this skin',
                iconCls:'settings',
                menu: {
                    items: [
                        {
                            text: 'Blue Theme',
                            handler: function()
                            {
                                Ext.util.CSS.swapStyleSheet('proto-theme', '');
                                Ext.util.CSS.swapStyleSheet('proto-theme-type', 'static/css/light.css');
                                changeColorScheme('blue');
                            }
                        },
                        {
                            text: 'Gray Theme (Default)',
                            handler: function()
                            {
                                Ext.util.CSS.swapStyleSheet('proto-theme', 'static/ext-js/resources/css/xtheme-gray.css');
                                Ext.util.CSS.swapStyleSheet('proto-theme-type', 'static/css/light.css');
                                changeColorScheme('grey');
                            }
                        },
                        {
                            text: 'Black Theme',
                            handler: function()
                            {
                                Ext.util.CSS.swapStyleSheet('proto-theme', 'static/ext-js/resources/css/xtheme-slickness.css');
                                Ext.util.CSS.swapStyleSheet('proto-theme-type', 'static/css/dark.css');
                                changeColorScheme('black');
                            }
                        }
                    ]
                }
            },
            {
                text: 'Shutdown SABnzbd',
                handler:function(e){Ext.MessageBox.confirm('Confirm', 'Are you sure you want to close SABnzbd?', shutdownProgram);}
            }]
        }); 
  

    statusTemplate = new Ext.Toolbar.TextItem({
                    text:'Loading',
                    tooltip:'Loading.',
                    id:'statusReplace'
                });
  
  
    var queuePause = new Ext.Toolbar.Button({
                    text:'Pause Queue',
                    tooltip:'Pause downloading of the queue.',
                    iconCls:'icon-pause',
                    id:'queuePauseButton',
                    enableToggle: true,
                    minWidth:110,
                    toggleHandler: pausetoggle
                });
                
     var speedbox = new Ext.form.TextField({
            width:35,
            listeners: {
                change: {
                    fn : limitSpeed,
                    value : 'frog'
                }
            },
            selectOnFocus:true
        });
        
     var queueActionCombo = new Ext.form.ComboBox({
            typeAhead: true,
            triggerAction: 'all',
            transform:'actionqfin',
            emptyText:'Action on queue finish...',
            width:150,
            lazyRender:true,
            listeners: {
                change: {
                    fn : queueFinishAction,
                    value : 'frog'
                }
            },
            selectOnFocus:true
        });
  
  
// create the top toolbar

    var tb = new Ext.Toolbar('toolbar');
    
    tb.add({
            id:'sabnzbd',
            text:'SABnzbd',
            disabled:false,
            tooltip:'SABnzbd version 0.5.0 pre-alpha',
            iconCls:'icon-fileinfo',
            menu:sabMenu
        },'-',  
        {
            //pause
            text:'',
            tooltip:'Pause an individual queue item (p)',
            iconCls:'icon-pause',
            minWidth:26,
            handler: pauseSelected
        },{ 
            //resume
            text:'',
            tooltip:'Resume an individual queue item (r)',
            iconCls:'icon-play',
            minWidth:26,
            handler: resumeSelected
        },
        new Ext.Toolbar.MenuButton(
        {
            text:'',
            tooltip:'Remove Selected items (del)',
            iconCls:'remove',
            minWidth:38,
            handler: removeSelected,
            // Menus can be built/referenced by using nested menu config objects
            menu : {items: [
                {text: 'Remove All',iconCls:'remove', handler: deleteAll}
            ]}
        }),
        {
            text:'',
            tooltip:'Change the priority on selected item: high(h)/normal(n)/low(l)',
            iconCls:'normal_priority',
            minWidth:38,
            // Menus can be built/referenced by using nested menu config objects
            menu : {items: [
                {text: 'High Priority',iconCls:'high_priority', handler: highPrioritySelected},
                {text: 'Normal Priority',iconCls:'normal_priority', handler: normalPrioritySelected},
                {text: 'Low Priority',iconCls:'low_priority', handler: lowPrioritySelected}
            ]}
        }
        ,'-', queuePause,' ',
        '-',
        ' Speed Limit: ',speedbox,'KB/s','-',
        queueActionCombo,
        '->', statusTemplate
    );

// hist toolbar
    var historyToolbar = new Ext.Toolbar.MenuButton(
                {
                    text:'',
                    tooltip:'Remove Selected items',
                    iconCls:'remove',
                    handler: removeSelectedHistory,
                    // Menus can be built/referenced by using nested menu config objects
                    menu : {items: [
                        {text: 'Remove All',iconCls:'remove', handler: deleteAllHistory}
                    ]}
                });
        
        
//-------------------------------------------------------------------------------------------------------------
//                                                              GRIDS
//-------------------------------------------------------------------------------------------------------------


    var historyGridView = new Ext.grid.GridView({ 
       //from http://extjs.com/learn/Ext_FAQ#Maintain_GridPanel_scroll_position_across_Store_reloads
       //with modifications by keckeroo http://extjs.com/forum/showthread.php?p=165216#post165216
        onLoad: Ext.emptyFn,
        autoFill: true,
        forceFit: true,
        listeners: {
            beforerefresh: function(v) {
               v.scrollTop = v.scroller.dom.scrollTop;
               v.scrollHeight = v.scroller.dom.scrollHeight;
            },
            refresh: function(v) {
               v.scroller.dom.scrollTop = v.scrollTop + (v.scrollTop == 0 ? 0 : v.scroller.dom.scrollHeight - v.scrollHeight);
            }
        }
    });  //end historyGridView 
    
    
    var historyPaging = new Ext.PagingToolbar({
        pageSize: 50,
        store: storeHistory,
        displayInfo: true,
        displayMsg: '{0}-{1}/{2}',
        emptyMsg: "No items to display"
        
    })
    historyPaging.on({
        render:{fn: addHistoryButton}
    });
    function addHistoryButton() {
    historyPaging.add(historyToolbar);}

    //history grid
    var historyGrid = new Ext.grid.GridPanel(
    {
        store: storeHistory,
        view: historyGridView,
            columns: [
            historyGridExpander,
            {
                header: "Job",
                id: "historyid",
                width: 35,
                sortable: true,
                dataIndex: 'id'
            },{
                header: "Filename",
                id: "historyFilename",
                width: 170,
                sortable: true,
				hideable: false,
                dataIndex: 'filename'
            },{
                header: "Status",
                width: 40,
                sortable: true,
                dataIndex: 'status',
                renderer: historyStatus
            },
            delhistory],
            plugins:[delhistory,historyGridExpander],
            viewConfig: {
                forceFit: true
            },
	        bbar: historyPaging,
			/*tbar:[
            historyToolbar
            ],*/
            width: 225,
            height: 250,
            //autoHeight:true,
            //autoExpandColumn:'Filename',
            //autoFitColumns: true,
            iconCls: 'icon-fileinfo',
            enableDragDrop:false
    });
    
    
    var gridView = new Ext.grid.GridView({ 
        //color the ROWS based on priority
        /*getRowClass : function (row, index) { 
          var cls = ''; 
          var data = row.data; 
          switch (data.priority) { 
             case 'High' : 
                cls = 'green-row' 
                break; 
             case 'Low' : 
                cls = 'red-row' 
                break;  
          }//end switch 
          return cls; 
       },*/
       //color the ROWS based on status
        getRowClass : function (row, index) { 
          var cls = ''; 
          var data = row.data; 
          switch (data.status) { 
             case 'Downloading' : 
                cls = 'downloading-row' 
                break; 
             case 'Paused' : 
                cls = 'paused-row' 
                break;  
          }//end switch 
          return cls; 
       },
       
       
       //remove both to enable horizontal scrolling
        autoFill: true,
        forceFit: true,
       //from http://extjs.com/learn/Ext_FAQ#Maintain_GridPanel_scroll_position_across_Store_reloads
       //with modifications by keckeroo http://extjs.com/forum/showthread.php?p=165216#post165216
        onLoad: Ext.emptyFn,
        listeners: {
            beforerefresh: function(v) {
               v.scrollTop = v.scroller.dom.scrollTop;
               v.scrollHeight = v.scroller.dom.scrollHeight;
            },
            refresh: function(v) {
               v.scroller.dom.scrollTop = v.scrollTop + (v.scrollTop == 0 ? 0 : v.scroller.dom.scrollHeight - v.scrollHeight);
            }
        }
    });  //end gridView 

    
    //queue grid
    queueGrid = new Ext.grid.EditorGridPanel(
    {
        store: store,
        clicksToEdit:1,
        id:'queuegrid',
        ddGroup: 'testDDGroup',
        view: gridView,
        columns: [{
            id: 'order',
            header: "Order",
            width: 35,
            sortable: true,
            dataIndex: 'index',
            editor: new Ext.form.ComboBox({               
                fieldLabel: 'Index',
                store: store,
                displayField:'index',
                typeAhead: true,
                triggerAction: 'all',
                selectOnFocus:true
            })
            },{
                header: "Name",
                id: "Name",
                width: 200,
                sortable: true,
				hideable: false,
                dataIndex: 'name'
                /*,editor: new Ext.form.TextArea ({
                    allowBlank:false,
                    grow:true,
                    growMin:20
                })*/
            },{
                header: "Status",
                width: 70,
                sortable: false,
                dataIndex: 'status'
                //enable for background cell colouring based on current status
                //,renderer: statusRender
            }, {
                header: "Percent",
                renderer: progressvar,
                width: 100,
                sortable: true,
                dataIndex: 'percentage'
            },{
                header: "Timeleft",
                width: 70,
                sortable: false,
                dataIndex: 'timeleft'
            },{
                header: "ETA",
                width: 70,
                sortable: false,
				hidden: true,
                dataIndex: 'eta'
            },{
                header: 'Priority',
                width: 70,
                sortable: false,
                dataIndex: 'priority'
                //enable to color the CELLS based on priority
                ,renderer: priorityRenderer
            }, {
                header: "Size",
                width: 60,
                sortable: true,
                dataIndex: 'bytes',
                renderer: fileSizes
            },{
                header: "Options",
                width: 60,
                sortable: false,
                dataIndex: 'unpackopts',
                editor: new Ext.form.ComboBox({
                    store: storeUnpack,
                    displayField: 'unpackopts',
                    typeAhead: true,
                    triggerAction: 'all',
                    mode: 'local',
                    selectOnFocus:true
                })
            },{
                header: "Script",
                width: 60,
                sortable: false,
                dataIndex: 'script',
                editor: new Ext.form.ComboBox({
                    store: storeScripts,
                    displayField:'script',
                    typeAhead: true,
                    triggerAction: 'all',
                    mode: 'local',
                    selectOnFocus:false,
                    listeners: {
                        focus: {
                            fn : function(){}
                        }
                    }
                })
            },{
                header: "Cat",
                width: 60,
                sortable: false,
                dataIndex: 'cat',
                editor: new Ext.form.ComboBox({
                    fieldLabel: 'Category',
                    store: storeCats,
                    displayField:'category',
                    typeAhead: true,
                    triggerAction: 'all',
                    selectOnFocus:true
                })
            },{
                header: "Age",
                width: 20,
                sortable: true,
                dataIndex: 'avg_age'
            },
            pauqueue,delqueue],
            plugins:[delqueue,pauqueue],
            viewConfig: {
                forceFit: true
            },
            sm: new Ext.grid.RowSelectionModel({
                singleSelect: false
            }),
            // inline toolbars
            width: 600,
            height: 300,
            //autoExpandColumn:'Filename',
            autoFitColumns: true,
            iconCls: 'icon-grid',
            enableDragDrop:true,
            listeners: {
                rowclick: {
                    fn : loadFiles
                },
                afteredit: {
                    fn : updateGrid,
                    value : 'frog'
                },
                render: function(g) {

                
                            // Best to create the drop target after render, so we don't need to worry about whether grid.el is null

                            // constructor parameters:
                            //    grid (required): GridPanel or EditorGridPanel (with enableDragDrop set to true and optionally a value specified for ddGroup, which defaults to 'GridDD')
                            //    config (optional): config object
                            // valid config params:
                            //    anything accepted by DropTarget
                            //    listeners: listeners object. There are 4 valid listeners, all listed in the example below
                            //    copy: boolean. Determines whether to move (false) or copy (true) the row(s) (defaults to false for move)
                            var ddrow = new Ext.ux.dd.GridReorderDropTarget(g, {
                                copy: false
                                ,listeners: {
                                    beforerowmove: function(objThis, oldIndex, newIndex, records) {
                                        // code goes here
                                        // return false to cancel the move
                                    }
                                    ,afterrowmove: function(objThis, oldIndex, newIndex, records) {

                                        for(i = 0; i < records.length; i++){
                                            //idx1 = records[newIndex].data.index;
                                            idx2 = newIndex;
                                            url = 'tapi?mode=switch&value='+records[i].data.nzo_id+'&value2='+idx2;
                                            Ext.Ajax.request(
                                            {
                                               url: url,
                                               success: dummy,
                                               failure: dummy
                                            });
                                        }
                                    }
                                    ,beforerowcopy: function(objThis, oldIndex, newIndex, records) {
                                        // code goes here
                                        // return false to cancel the copy
                                    }
                                    ,afterrowcopy: function(objThis, oldIndex, newIndex, records) {
                                        // code goes here
                                    }
                                }
                            });

                            // if you need scrolling, register the grid view's scroller with the scroll manager
                            Ext.dd.ScrollManager.register(g.getView().getEditorParent());
                        }
                        ,beforedestroy: function(g) {
                            // if you previously registered with the scroll manager, unregister it (if you don't it will lead to problems in IE)
                            Ext.dd.ScrollManager.unregister(g.getView().getEditorParent());
                        }
            },
	        bbar: new Ext.PagingToolbar({
	            pageSize: 50,
	            store: store,
	            displayInfo: true,
	            displayMsg: 'Displaying {0} - {1} of {2}',
	            emptyMsg: "No items to display"
	        })


    });
    


   
//-------------------------------------------------------------------------------------------------------------
//                                                      VIEWPORT
//-------------------------------------------------------------------------------------------------------------
    
   var viewport = new Ext.Viewport({
        layout:'border',
        id:'viewport',
        hideBorders:true,
        items:[
            { // raw
                region:'north',
                el: 'north',
                frame:false,
                autoHeight:true,
                margins:'0 0 0 0'
            },{
                region:'south',
                split:true,
                height: 200,
                minSize: 100,
                maxSize: 400,
                id: 'south',
                collapsible: true,
                collapseMode:'mini',
                title:'South',
                margins:'0 0 0 0',
                header:false,
                listeners: {
                    resize: function(one, newWidth,newHeight) {
                    southHeight = newHeight;
                    drawChart();
                    resizeBottom();
                    }
                },
                items:southTabs
            },{
                region:'east',
                id: 'east',
                collapsible: true,
                split:true,
                collapseMode:'mini',
                width: 325,
                minSize: 300,
                maxSize: 800,
                layout:'fit',
                margins:'0 0 0 0',
                items:historyGrid
             },{
                region: 'center',
                id: 'center',
                layout: 'fit',
                margins: '0 0 0 0',
                items:queueGrid
                
            }]
    });
    

    
//-------------------------------------------------------------------------------------------------------------
//                                                       MISC
//-------------------------------------------------------------------------------------------------------------


// Key Mapping

    var queueMap = new Ext.KeyMap("center", [
        {key: 46,fn: function(){ removeSelected(); }},
        {key: 'h',fn: function(){ highPrioritySelected(); }},
        {key: 'n',fn: function(){ normalPrioritySelected(); }},
        {key: 'l',fn: function(){ lowPrioritySelected(); }},
        {key: 'p',fn: function(){ pauseSelected(); }},
        {key: 'r',fn: function(){ resumeSelected(); }}

    ]);

    var historyMap = new Ext.KeyMap("east", [
        {
            key: 46,
            fn: function(){ removeSelectedHistory(); }
        }
    ]);
    
    /*var globalMap = new Ext.KeyMap("sab", [
        {
            key: 'a',
            fn: function(){ alert('you pressed a!!!'); }
        }
    ]);*/


var globalRefresh = {
    run: function(){
        store.reload();
        storeFiles.reload();
        storeHistory.reload();
        storeStatus.reload();
        storeWarnings.reload();
    },
    interval: 5000 //5 seconds
}
var runner = new Ext.util.TaskRunner();
runner.start(globalRefresh);

}); //onreader function


