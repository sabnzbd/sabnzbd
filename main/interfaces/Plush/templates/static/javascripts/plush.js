var refreshRate = 8; // default refresh rate
var skipRefresh = false;
var focusedOnSpeedChanger = false;
var queue_view_preference = 15;
var history_view_preference = 15;

// once the DOM is ready, run this
$(document).ready(function(){
	
	// IE6 png transparency issues
	$('img[@src$=.png], div.history_logo, a.queue_logo, li.q_menu_addnzb, li.q_menu_pause, li.h_menu_verbose, li.h_menu_purge, div#time-left, div#speed').ifixpng();
	
	// main menu
	$(".nav").superfish({
		animation	: { opacity:"show", height:"show" },
		hoverClass	: "sfHover",
		delay		: 800,
		animation	: {opacity:"show"},
		speed		: "normal"
	});
	
	// drag & drop that will extend over multiple refreshes (for Queue)
	$('#queueTable').livequery(function() {
		
		$('#queue_view_preference').change(function(){
			queue_view_preference = $('#queue_view_preference').val();
			SetCookie('queue_view_preference',queue_view_preference);
			RefreshTheQueue();
		});
		
		InitiateDragAndDrop(); // also called when queue is manually refreshed
		
		$('#queueTable .title').dblclick(function(){
			$(this).parent().parent().prependTo('#queueTable');
			$.ajax({
				type: "GET",
				url: "queue/switch?uid1="+$(this).parent().parent().attr('id')+"&uid2=0&dummy="+Math.random()
			});
		});
		
		// processing option changes
		$('#queueTable .proc_category').change(function(){
			$.ajax({
				type: "GET",
				url: 'queue/change_cat?dummy='+Math.random()+'&nzo_id='+$(this).parent().parent().attr('id')+'&cat='+$(this).val()
			});
		});
		$('#queueTable .proc_option').change(function(){
			$.ajax({
				type: "GET",
				url: 'queue/change_opts?dummy='+Math.random()+'&nzo_id='+$(this).parent().parent().attr('id')+'&pp='+$(this).val()
			});
		});
		$('#queueTable .proc_script').change(function(){
			$.ajax({
				type: "GET",
				url: 'queue/change_script?dummy='+Math.random()+'&nzo_id='+$(this).parent().parent().attr('id')+'&script='+$(this).val()
			});
		});
		
		// skip queue refresh on mouseover
		$('#queueTable').bind("mouseover", function(){ skipRefresh=true; });
		$('#queueTable').bind("mouseout", function(){ skipRefresh=false; });
		$('.box_fatbottom').bind("mouseover mouseout", function(){ skipRefresh=false; });
		
	});
	
	// tooltips that will extend over multiple refreshes (for History)
	$('#history div').livequery(function() {
		
		$('#history_view_preference').change(function(){
			history_view_preference = $('#history_view_preference').val();
			SetCookie('history_view_preference',history_view_preference);
			RefreshTheHistory();
		});
		
		$(this).Tooltip({
			extraClass:	"tooltip",
			track:		true, 
			fixPNG:		true
		});
		
	});
	
	// set up more tooltips for main screen
	$('.tip').Tooltip({
			extraClass:	"tooltip",
			track:		true, 
			fixPNG:		true
	});
	
	// restore Add NZB from cookie
	if (ReadCookie('Plush2AddNZB') != 'block')
		$('#add_nzb_menu').css('display','block');
	else
		$('#add_nzb_menu').css('display','none');
	
	// restore queue/history view preferences
	if (ReadCookie('queue_view_preference'))
		queue_view_preference = ReadCookie('queue_view_preference');
	if (ReadCookie('history_view_preference'))
		history_view_preference = ReadCookie('history_view_preference');
	
	// restore Refresh rate from cookie
	if (ReadCookie('Plush2Refresh'))
		refreshRate = ReadCookie('Plush2Refresh');
	else
		SetCookie('Plush2Refresh',refreshRate);
	
	// set Refresh rate within main menu	
	$("#refreshRate-option").val(refreshRate);
	$("#refreshRate-option").change( function() {
		reactivate = false;
		if (refreshRate == 0)
			reactivate = true;
		refreshRate = $("#refreshRate-option").val();
		SetCookie('Plush2Refresh',refreshRate);
		if (refreshRate > 0 && reactivate)
			MainLoop();
	});
	
	// "KB/s Max Speed" main menu input
	$("#maxSpeed-option").focus( function() {
		focusedOnSpeedChanger = true;
	});
	$("#maxSpeed-option").blur( function() {
		focusedOnSpeedChanger = false;
	});
	$("#maxSpeed-option").change( function() {
		$.ajax({
			type: "GET",
			url: "api?mode=config&name=set_speedlimit&value="+$("#maxSpeed-option").val()+"&dummy="+Math.random()
		});
	});
	
	// "On Queue Finish" main menu item menu select
	$("#onQueueFinish-option").change( function() {
		$.ajax({
			type: "GET",
			url: "queue/change_queue_complete_action?action="+$("#onQueueFinish-option").val()+"&dummy="+Math.random()
		});
	});
	
	// sort queue (3 options from main menu)
	$('#sort_by_avg_age').click(function(event) {
		$.ajax({
			type: "GET",
			url: "queue/sort_by_avg_age?dummy="+Math.random(),
			success: function(result){
				return LoadTheQueue(result);
			}
		});
	});
	$('#sort_by_name').click(function(event) {
		$.ajax({
			type: "GET",
			url: "queue/sort_by_name?dummy="+Math.random(),
			success: function(result){
				return LoadTheQueue(result);
			}
		});
	});
	$('#sort_by_size').click(function(event) {
		$.ajax({
			type: "GET",
			url: "queue/sort_by_size?dummy="+Math.random(),
			success: function(result){
				return LoadTheQueue(result);
			}
		});
	});
	
	// purge queue
	$('#queue_purge').click(function(event) {
		if(confirm('Sure you want to clear out your Queue?')){
			$.ajax({
				type: "GET",
				url: "queue/purge?dummy="+Math.random(),
				success: function(result){
					return LoadTheQueue(result);
				}
			});
		}
	});
	
	// "Add NZB" horiz. bar toggler from main menu
	$('#add_nzb_menu_toggle_upper').bind('click', function() {
		$('#add_nzb_menu').slideToggle("fast", SetCookie('Plush2AddNZB',$('#add_nzb_menu').css('display')) );
	});
	
	// Set up +NZB by URL/Newzbin Report ID
	$('#addID').bind('click', function() { 
		$.ajax({
			type: "GET",
			url: "addID",
			data: "id="+$("#addID_input").val()+"&pp="+$("#addID_pp").val()+"&script="+$("#addID_script").val()+"&cat="+$("#addID_cat").val(),
			success: function(result){
				return RefreshTheQueue();
			}
		});
		$("#addID_input").val('enter URL/ID');
	});
	$('#addID_input').val('enter URL/ID').focus( function(){
		if ($(this).val()=="enter URL/ID")
			$(this).val('');
	}).blur( function(){
		if (!$(this).val())
			$(this).val('enter URL/ID');
	});
	
	// set up +NZB by file upload
	$('#uploadNZBForm').submit( function(){
		return AIM.submit(this, {'onComplete': RefreshTheQueue})
	});
	
	// toggle queue shutdown - from options menu
	if ($('#queue_shutdown_option')) {
		$('#queue_shutdown_option').bind('click', function() { 
			if(confirm('Are you sure you want to toggle shutting down your entire computer when the queue downloads have finished?')){
				$.ajax({
					type: "GET",
					url: "queue/tog_shutdown?dummy="+Math.random(),
					success: function(result){
						return LoadTheQueue(result);
					}
				});
			}
		});
	}
	
	// set up "shutdown sabnzbd" from main menu
	$('#shutdown_sabnzbd').click( function(){
		if(confirm('Sure you want to shut down the SABnzbd application?'))
			window.location='shutdown';
	});
	
	// pause / resume
	$('#pause_resume').click(function(event) {
		if ($(event.target).attr('class') == 'tip q_menu_pause q_menu_paused')
			$.ajax({
				type: "GET",
				url: "api?mode=resume&dummy="+Math.random()
			});
		else
			$.ajax({
				type: "GET",
				url: "api?mode=pause&dummy="+Math.random()
			});
		if ($('#pause_resume').attr('class') == 'tip q_menu_pause q_menu_paused')
			$('#pause_resume').attr('class','tip q_menu_pause q_menu_unpaused');
		else
			$('#pause_resume').attr('class','tip q_menu_pause q_menu_paused');
	});
	
	// Set up Queue Menu actions
	$('#queue').click(function(event) {
		if ($(event.target).is('.queue_delete') && confirm('Delete NZB? Are you sure?') ) {
			delid = $(event.target).parent().parent().attr('id');
			$('#'+delid).fadeOut('fast');
			$.ajax({
				type: "GET",
				url: 'queue/delete?dummy='+Math.random()+'&uid='+delid
			});
		}
	});
	
	// history verbosity
	$('.h_menu_verbose').click(function(event) {
		$.ajax({
			type: "GET",
			url: 'history/tog_verbose?dummy='+Math.random(),
			success: function(result){
				return $('#history').html(result);
			}
		});
	});
	
	// history purge
	$('.h_menu_purge').dblclick(function(event) {
		$.ajax({
			type: "GET",
			url: 'history/purge?dummy='+Math.random(),
			success: function(result){
				return $('#history').html(result);
			}
		});
	});
	
	// Set up History Menu actions
	$('#history').click(function(event) {
		if ($(event.target).is('.queue_delete')) {	// history delete
			delid = $(event.target).parent().parent().attr('id');
			$('#'+delid).fadeOut('fast');
			$.ajax({
				type: "GET",
				url: 'history/delete?dummy='+Math.random()+'&job='+delid
			});
		}
	});
	
	// initiate refreshes
	MainLoop();
	
});

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
		url: 'queue/?limit='+limit+'&dummy='+Math.random(),
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
		url: 'history/?limit='+limit+'&dummy='+Math.random(),
		success: function(result){
			return $('#history').html(result);
		}
	});
}

// refresh the queue with supplied data (like if we already made an AJAX call)
function LoadTheQueue(result) {
	$('#queue').html(result);
	if ($('#stats_noofslots').html()!='0')
		InitiateDragAndDrop();
}

// called upon every refresh
function InitiateDragAndDrop() {
	$("#queueTable").tableDnD({
		onDrop: function(table, row) {
			var rows = table.tBodies[0].rows;
			
			if (rows.length < 2)
				return false;
			
			// figure out which position dropped row is at now
			for ( var i=0; i < rows.length; i++ )
				if (rows[i].id == row.id)
					return $.ajax({
						type: "GET",
						url: "queue/switch?uid1="+row.id+"&uid2="+i+"&dummy="+Math.random()
					});
			return false;
		}
	});	
}

// used to store refresh rate
function SetCookie(name,val) {
	var date = new Date();
	date.setTime(date.getTime()+(365*24*60*60*1000));
	document.cookie = name+"="+val+"; expires="+ date.toGMTString() +"; path=/";
}

// used during initialization to restore refresh rate
function ReadCookie(name) {
	var nameEQ = name + "=";
	var ca = document.cookie.split(';');
	for(var i=0;i < ca.length;i++) {
		var c = ca[i];
		while (c.charAt(0)==' ') c = c.substring(1,c.length);
		if (c.indexOf(nameEQ) == 0) return c.substring(nameEQ.length,c.length);
	}
	return null;
}
