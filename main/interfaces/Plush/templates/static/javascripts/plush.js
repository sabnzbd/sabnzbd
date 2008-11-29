var refreshRate = 30; // default refresh rate
var skipRefresh = false;
var focusedOnSpeedChanger = false;
var queue_view_preference = 15;
var history_view_preference = 15;


// once the DOM is ready, run this
$(document).ready(function(){
	
	/********************************************
	*********************************************

		NZB Processing Methods
		
	*********************************************
	********************************************/
	
	
	// Fetch NZB by URL/Newzbin Report ID
	$('#addID').bind('click', function() { 
		if ($('#addID_input').val()!='enter URL / Newzbin ID') {
			$.ajax({
				type: "GET",
				url: "addID",
				data: "id="+$("#addID_input").val()+"&pp="+$("#addID_pp").val()+"&script="+$("#addID_script").val()+"&cat="+$("#addID_cat").val(),
				success: function(result){
					return RefreshTheQueue();
				}
			});
			$("#addID_input").val('enter URL / Newzbin ID');
		}
	});
	$('#addID_input').val('enter URL / Newzbin ID')
	.focus( function(){
		if ($(this).val()=="enter URL / Newzbin ID")
			$(this).val('');
	}).blur( function(){
		if (!$(this).val())
			$(this).val('enter URL / Newzbin ID');
	});
	
	
	// NZB File Upload
	$('#addNZBbyFile').upload({
        name: 'name',
        action: 'api',
        enctype: 'multipart/form-data',
        params: {mode: "addfile", pp: $("#addID_pp").val(), script: $("#addID_script").val(), cat: $("#addID_cat").val()},
        autoSubmit: true,
        onComplete: RefreshTheQueue
		//onSubmit: function() {},
        //onSelect: function() {}
	});
	
	
	/********************************************
	*********************************************

		Main Menu Methods
		
	*********************************************
	********************************************/


	// activate main menu (shown upon hovering SABnzbd logo)
	$("ul.sf-menu").superfish({
		pathClass:  'current'
	});
	
	
	// restore Refresh rate from cookie
	if ($.cookie('Plush2Refresh'))
		refreshRate = $.cookie('Plush2Refresh');
	else
		$.cookie('Plush2Refresh', refreshRate, { expires: 365 });


	// Refresh Rate main menu input
	$("#refreshRate-option").val(refreshRate);
	$("#refreshRate-option").change( function() {
		reactivate = false;
		if (refreshRate == 0)
			reactivate = true;
		refreshRate = $("#refreshRate-option").val();
		$.cookie('Plush2Refresh', refreshRate, { expires: 365 });
		if (refreshRate > 0 && reactivate)
			MainLoop();
	});
	
	
	// Max Speed main menu input
	$("#maxSpeed-option").focus( function() {
		focusedOnSpeedChanger = true;
	});
	$("#maxSpeed-option").blur( function() {
		focusedOnSpeedChanger = false;
	});
	$("#maxSpeed-option").change( function() {
		$.ajax({
			type: "GET",
			url: "api?mode=config&name=set_speedlimit&value="+$("#maxSpeed-option").val()+"&_dc="+Math.random()
		});
	});
	
	
	// On Queue Finish main menu select
	$("#onQueueFinish-option").change( function() {
		$.ajax({
			type: "GET",
			url: "api?mode=queue&name=change_complete_action&value="+$("#onQueueFinish-option").val()+"&_dc="+Math.random()
		});
	});
	
	
	// Sort Queue main menu options
	$('#sort_by_avg_age').click(function(event) {
		$.ajax({
			type: "GET",
			url: "queue/sort_by_avg_age?_dc="+Math.random(),
			success: function(result){
				return RefreshTheQueue();
			}
		});
	});
	$('#sort_by_name').click(function(event) {
		$.ajax({
			type: "GET",
			url: "queue/sort_by_name?_dc="+Math.random(),
			success: function(result){
				return RefreshTheQueue();
			}
		});
	});
	$('#sort_by_size').click(function(event) {
		$.ajax({
			type: "GET",
			url: "queue/sort_by_size?_dc="+Math.random(),
			success: function(result){
				return RefreshTheQueue();
			}
		});
	});

	
	// set up "shutdown sabnzbd" from main menu
	$('#shutdown_sabnzbd').click( function(){
		if(confirm('Sure you want to shut down the SABnzbd application?'))
			window.location='shutdown';
	});
	

	/********************************************
	*********************************************

		Queue Methods
		
	*********************************************
	********************************************/


	// this code will remain instantiated even when the contents of the queue change
	$('#queueTable').livequery(function() {
		
		$('#queue_view_preference').change(function(){
			$.cookie('queue_view_preference', $('#queue_view_preference').val(), { expires: 365 });
			RefreshTheQueue();
		});
		
		// queue sorting
		InitiateQueueDragAndDrop();
		
		$('#queueTable .title').dblclick(function(){
			$(this).parent().parent().prependTo('#queueTable');
			$.ajax({
				type: "GET",
				url: "api?mode=switch&value="+$(this).parent().parent().attr('id')+"&value2=0&_dc="+Math.random()
			});
		});
		
		// processing option changes
		$('#queueTable .proc_category').change(function(){
			$.ajax({
				type: "GET",
				url: 'api?mode=change_cat&value='+$(this).parent().parent().attr('id')+'&value2='+$(this).val()+'&_dc='+Math.random()
			});
		});
		$('#queueTable .proc_option').change(function(){
			$.ajax({
				type: "GET",
				url: 'api?mode=change_opts&value='+$(this).parent().parent().attr('id')+'&value2='+$(this).val()+'&_dc='+Math.random()
			});
		});
		$('#queueTable .proc_script').change(function(){
			$.ajax({
				type: "GET",
				url: 'api?mode=change_script&value='+$(this).parent().parent().attr('id')+'&value2='+$(this).val()+'&_dc='+Math.random()
			});
		});
		
		// skip queue refresh on mouseover
		$('#queueTable').bind("mouseover", function(){ skipRefresh=true; });
		$('#queueTable').bind("mouseout", function(){ skipRefresh=false; });
		$('.box_fatbottom').bind("mouseover mouseout", function(){ skipRefresh=false; });
		
	}); // end livequery
	
	
	// queue pause/resume
	$('#pause_resume').click(function(event) {
		if ($(event.target).attr('class') == 'tip q_menu_pause q_menu_paused')
			$.ajax({
				type: "GET",
				url: "api?mode=resume&_dc="+Math.random()
			});
		else
			$.ajax({
				type: "GET",
				url: "api?mode=pause&_dc="+Math.random()
			});
		if ($('#pause_resume').attr('class') == 'tip q_menu_pause q_menu_paused')
			$('#pause_resume').attr('class','tip q_menu_pause q_menu_unpaused');
		else
			$('#pause_resume').attr('class','tip q_menu_pause q_menu_paused');
	});


	// queue purge
	$('#queue_purge').click(function(event) {
		if(confirm('Sure you want to empty out your Queue?')){
			$.ajax({
				type: "GET",
				url: "api?mode=queue&name=delete&value=all&_dc="+Math.random(),
				success: function(result){
					return RefreshTheQueue();
				}
			});
		}
	});
	
	
	// queue nzb deletion
	$('#queue').click(function(event) {
		if ($(event.target).is('.queue_delete') && confirm('Delete NZB? Are you sure?') ) {
			delid = $(event.target).parent().parent().attr('id');
			$('#'+delid).fadeOut('fast');
			$.ajax({
				type: "GET",
				url: 'api?mode=queue&name=delete&value='+delid+'&_dc='+Math.random()
			});
		}
	});
	
	
	/********************************************
	*********************************************

		History Methods
		
	*********************************************
	********************************************/


	// history verbosity toggle
	$('.h_menu_verbose').click(function(event) {
		$.ajax({
			type: "GET",
			url: 'history/tog_verbose?_dc='+Math.random(),
			success: function(result){
//				return RefreshTheHistory();
				return $('#history').html(result); // is this loading the history twice? redirect?
			}
		});
	});
	
	
	// history purge
	$('.h_menu_purge').dblclick(function(event) {
		$.ajax({
			type: "GET",
			url: 'api?mode=history&name=delete&value=all&_dc='+Math.random(),
			success: function(result){
				RefreshTheHistory();
			}
		});
	});
	
	
	// history nzb deletion
	$('#history').click(function(event) {
		if ($(event.target).is('.queue_delete')) {	// history delete
			delid = $(event.target).parent().parent().attr('id');
			$('#'+delid).fadeOut('fast');
			$.ajax({
				type: "GET",
				url: 'api?mode=history&name=delete&value='+delid+'&_dc='+Math.random()
			});
		}
	});
	
	
	// this code will remain instantiated even when the contents of the history change
	$('#history .left_stats').livequery(function() {
		// history view limiter
		$('#history_view_preference').change(function(){
			$.cookie('history_view_preference', $('#history_view_preference').val(), { expires: 365 });
			RefreshTheHistory();
		});
	});
	
	
	// this code will remain instantiated even when the contents of the history change
	$('#history .last div').livequery(function() {
		// tooltips for verbose notices
		$(this).tooltip({
			extraClass:	"tooltip",
			track:		true, 
			fixPNG:		true
		});
	});
	
	
	/********************************************
	*********************************************

		Miscellaneous Methods
		
	*********************************************
	********************************************/
	
	
	// restore queue/history view preferences
	if ($.cookie('queue_view_preference'))
		queue_view_preference = $.cookie('queue_view_preference');
	if ($.cookie('history_view_preference'))
		history_view_preference = $.cookie('history_view_preference');
	
	
	// additional tooltips
	$('.tip').tooltip({
		extraClass:	"tooltip",
		track:		true, 
		fixPNG:		true
	});
	
	
	// fix IE6 .png image transparencies
	$('img[@src$=.png], div.history_logo, div.queue_logo, li.q_menu_addnzb, li.q_menu_pause, li.h_menu_verbose, li.h_menu_purge, div#time-left, div#speed').ifixpng();


	// initiate refresh cycle
	MainLoop();
	
}); // end document onready


// calls itself after `refreshRate` seconds
function MainLoop() {
	
	// ajax calls
	RefreshTheQueue();
	RefreshTheHistory();
	
	// loop
	if (refreshRate > 0)
		setTimeout("MainLoop()",refreshRate*1000);
}


// in a function since some processes need to refresh the queue outside of MainLoop()
function RefreshTheQueue() {
	if (skipRefresh) return $('#skipped_refresh').fadeIn("slow").fadeOut("slow"); // set within queue <table>
	var limit = queue_view_preference;
	if ($('#queue_view_preference').val() != "")
		var limit = $('#queue_view_preference').val()
	$.ajax({
		type: "GET",
		url: 'queue/?dummy2='+limit+'&_dc='+Math.random(),
		success: function(result){
			return $('#queue').html(result);
		}
	});
}


// in a function since some processes need to refresh the queue outside of MainLoop()
function RefreshTheHistory() {
	var limit = history_view_preference;
	if ($('#history_view_preference').val() != "")
		var limit = $('#history_view_preference').val()
	$.ajax({
		type: "GET",
		url: 'history/?dummy2='+limit+'&_dc='+Math.random(),
		success: function(result){
			return $('#history').html(result);
		}
	});
}


// called upon every queue refresh
function InitiateQueueDragAndDrop() {
	$("#queueTable").tableDnD({
		onDrop: function(table, row) {
			var rows = table.tBodies[0].rows;
			
			if (rows.length < 2)
				return false;
			
			// determine which position the repositioned row is at now
			for ( var i=0; i < rows.length; i++ )
				if (rows[i].id == row.id)
					return $.ajax({
						type: "GET",
						url: "api?mode=switch&value="+row.id+"&value2="+i+"&_dc="+Math.random()
					});
			return false;
		}
	});	
}


/*
// disables toggler text selection when clicking
function disableSelection(element) {
    element.onselectstart = function() {
        return false;
    };
    element.unselectable = "on";
    element.style.MozUserSelect = "none";
    element.style.cursor = "default";
};
*/
