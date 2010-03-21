// assembled by pairofdimes through use of examples




	// ********************************************
	// ********************************************
	// ********************************************
	// ********************************************
	// ******************************************** layout

var PageLayout, Downloads, InnerLayout, $Tabs;

var showResizeMsgs = false;

var msg;

function resizeTabLayout () {
	if (!$Tabs) return; // make sure tabs are initialized
	var selected = $Tabs.tabs('option', 'selected');
	// ONLY resize the layout when first tab is 'visible'
	if (selected === 0) { // Tab #1 (index=1)
		msg = "";

		// now resize the outermost layout to fit the new container size...
		PageLayout.resizeAll(); // ...triggers cascading resize of inner-layouts - if initialized

		// make sure all inner-layouts are initialized and 'visible'
		initAppLayout();
	}
}

	function initAppLayout () {
		var $Container = $('#Downloads');

	// make sure Container element is not hidden
		$Container.show();
	// if Container is still not visible, then must be INSIDE a hidden element
	if ( !$Container.is(':visible') ) return; // ABORT

	// init the Layout if not already done
	if (!Downloads)
		Downloads = $Container.layout({
			name:						"Downloads"
		,	resizeWithWindow:			false
		,	triggerEventsOnLoad:		false
		,	center__paneSelector:		".outer-center"
		,	west__paneSelector:			".outer-west"
		,	east__paneSelector:			".outer-east"
		,	north__paneSelector:  		".outer-north"
		,	south__paneSelector:  		".outer-south"
		,	contentSelector:			".ui-widget-content"
		,	spacing_open:				4
		,	spacing_closed:				4
		,	north__minSize:				20
		,	north__spacing_open:		1
		,	north__togglerLength_open:	0
		,	north__togglerLength_close:	-1
		,	north__resizable:			false
		,	north__slidable:			false
		,	north__fxName:				'none'
		,	east__size:					520
		//,	west__initClosed:			true
		,	south__minSize:				5
		,	south__size:				100
		//,	south__size:				'auto'
		,	south__togglerLength_open:	0
		,	south__togglerLength_close:	-1
		,	south__resizable:			true
		,	south__slidable:			true
		,	south__spacing_open:		1
		,	center__onresize:			"InnerLayout.resizeAll"
		,	onresizeall_start:			function () { if (showResizeMsgs) alert( 'Downloads.onresizeall_start()' ); }
		,	onresizeall_end:			function () { if (showResizeMsgs) alert( 'Downloads.onresizeall_end()' ); }
		});

	// now show/init the inner layout
	initInnerLayout();
}

	function initInnerLayout () {
		var $Container = $('#InnerLayout');

	// make sure Container element is not hidden
		$Container.show();
	// if Container is still not visible, then must be INSIDE a hidden element
	if ( !$Container.is(':visible') ) return; // ABORT

	// init the Layout if not already done
		if (!InnerLayout)
		InnerLayout = $Container.layout({
			name:						"InnerLayout"
		,	triggerEventsOnLoad:		false
		,	center__paneSelector:		".inner-center"
		,	west__paneSelector:			".inner-west"
		,	east__paneSelector:			".inner-east"
		,	north__paneSelector:		".inner-north"
		,	contentSelector:			".ui-widget-content"
		,	west__initClosed:			true
		,	east__initClosed:			true
		//,	north__initClosed:			true
		//,	north__initHidden:			true
		,	spacing_open:				4
		,	spacing_closed:				4
		,	west__size:					361
		,	east__size:					400
		,	east__fxSpeed:				'slow'
		,	north__minSize:				15
		,	north__spacing_open:		2
		,	north__togglerLength_open:	50
		,	north__togglerLength_close:	-1
		,	onresizeall_start:			function () { if (showResizeMsgs) alert( 'InnerLayout.onresizeall_start()' ); }
		,	onresizeall_end:			function () { if (showResizeMsgs) alert( 'InnerLayout.onresizeall_end()' ); }
		});
}


$(document).ready(function () { 

	// best to create the tabs first, because is 'container' for the tab-layout (Downloads)
	$Tabs = $("#tabs").tabs({
		show: resizeTabLayout // resize layout EACH TIME the layout-tab becomes 'visible'
		//, disabled: [4,5,6]
	});
	
	$cTabs = $("#footertabs").tabs({
	});
	$cTabs = $("#configtabs").tabs({
	});
	$sTabs = $("#searchtabs").tabs({
	});
	

	// use different outer-layout classNames to simplify/clarify CSS
	PageLayout = $('body').layout({ 
		name:						"PageLayout"
	,	triggerEventsOnLoad:		false
	,	north__paneSelector:		"#TabButtons"
	,	center__paneSelector:		"#TabPanelsContainer"
	,	center__onresize:			"Downloads.resizeAll"
	,	spacing_open:				0
	/*	OLD - uses 1-pane with header & 'content' divs instead of north & center 'panes'
		center__paneSelector:		".page-layout-center"
	,	contentSelector:			"#TabPanelsContainer"
	*/
	});

	// resize div.ui-layout-ui-widget-content AFTER initializing the tabs
	PageLayout.resizeAll();

	// initialize the inner-layouts - IF CONTAINER-TAB IS VISIBLE
	initAppLayout();
	$('#tabs').tabs('option', 'selected', 0);


	
	
	
	
	
	// ********************************************
	// ********************************************
	// ********************************************
	// ********************************************
	// ******************************************** grid
	
	$.jgrid.defaults = $.extend($.jgrid.defaults,{loadui:"enable"});
	
	jQuery("#queueGrid").jqGrid({
		jsonReader : {
			root: "slots",
			records: "noofslots",
			repeatitems: false,
			id: "index"
		},
	    datatype: function(postdata) {
	        jQuery.ajax({
	           url: 'tapi?mode=queue&output=json&session='+apikey,
	           data:postdata,
	           dataType:"json",
	           complete: function(jsondata,stat){
	              if(stat=="success") {
	                 var thegrid = jQuery("#queueGrid")[0];
	                 var json = eval("("+jsondata.responseText+")").queue;
	                 json.page=1;
	                 thegrid.addJSONData(json);
	                 
	                 // update header stats
	                 switch(json.status){
	                 	case 'Downloading':	$('#stat-Status').css('color','lightgreen');break;
	                 	case 'Idle':		$('#stat-Status').css('color','yellow');	break;
	                 	case 'Paused':		$('#stat-Status').css('color','red');		break;
	                 };
	                 $('#stat-Status').html(json.status);
	                 $('#stat-Speed').html( parseInt(json.kbpersec) );
	                 $('#stat-Timeleft').html(json.timeleft);
	                 
	              }
	           }
	        });
	    },
		colNames:['Name','%','MB Left','Size','Age','Category','Priority','Processing','Script','Status'],
		colModel:[
			{name:'filename',index:'Name', width:300, editable:true},
			{name:'percentage',index:'%', width:20, sortable:false, align:"right"},
			{name:'mbleft',index:'MB Left', width:60, sortable:false, align:"right"},
			{name:'size',index:'Size', width:80, align:"right"},
			{name:'avg_age',index:'Age', width:36, align:"right"},
			{name:'cat',index:'Category', sortable:false, width:80},		
			{name:'priority',index:'Priority', sortable:false, width:80},		
			{name:'unpackopts',index:'Processing', width:80},		
			{name:'script',index:'Script', width:80},
			{name:'status',index:'Status', width:80}
		],
		rowNum:10,
		rowList:[10,20,30,999],
		caption: "Queue",
		autowidth: true, 
		height: '100%',
		imgpath: 'static/images/jqgrid/',
		sortname: 'index',
		sortorder: "asc",
		viewrecords: true,
		multiselect: true,
		pager: jQuery('#queueGridSub')

	});
	jQuery("#queueGrid").jqGrid('navGrid','#queueGridSub',{add:false,edit:false}); 
	jQuery("#queueGrid").jqGrid('navButtonAdd','#queueGridSub',{
		caption: "Columns",
		title: "Reorder Columns",
		onClickButton : function (){
			jQuery("#queueGrid").jqGrid('columnChooser');
		}
	});
	//jQuery("#queueGrid").jqGrid('gridResize');	
	
	
	
	jQuery("#historyGrid").jqGrid({
		jsonReader : {
			root: "slots",
			records: "noofslots",
			repeatitems: false,
			id: "index"
		},
	    datatype: function(postdata) {
	        jQuery.ajax({
	           url: 'tapi?mode=history&output=json&session='+apikey,
	           data:postdata,
	           dataType:"json",
	           complete: function(jsondata,stat){
	              if(stat=="success") {
	                 var thegrid = jQuery("#historyGrid")[0];
	                 var json = eval("("+jsondata.responseText+")").history;
	                 json.page=1;
	                 thegrid.addJSONData(json);
	              }
	           }
	        });
	    },
		colNames:['Name','Status','When'],
		colModel:[
			{name:'name',index:'Name', width:300},
			{name:'status',index:'Status', width:60},
			{name:'completed',index:'When', width:100, formatter:dateFmatter}		
		],
		rowNum:10,
		rowList:[10,20,30,999],
		caption: "History",
		autowidth: true, 
		height: '100%',
		imgpath: 'static/images/jqgrid/',
		sortname: 'index',
		sortorder: "asc",
		viewrecords: true,
		multiselect: true,
		pager: jQuery('#historyGridSub')

	});
	jQuery("#historyGrid").jqGrid('navGrid','#historyGridSub',{add:false,edit:false}); 
	jQuery("#historyGrid").jqGrid('navButtonAdd','#historyGridSub',{
		caption: "",
		title: "Reorder Columns",
		onClickButton : function (){
			jQuery("#historyGrid").jqGrid('columnChooser');
		}
	}); 
	//jQuery("#historyGrid").jqGrid('gridResize');	

	
	// format history 'completed' time to date
	function dateFmatter (cellvalue, options, rowObject) {
		var d = new Date();
		d.setTime(cellvalue*1000);
		return d.toDateString();
	}

});
	