
var refreshRate = 8; // default refresh rate
var skipRefresh = false;

// once the DOM is ready, run this
$(document).ready(function() {
	var windowSize = $(document).width();
	windowSize = windowSize/69;
	Math.round(windowSize);
	$(".nav").css("padding-left", windowSize + "%");
	
	// main menu
	$(".nav").superfish({
		animation : { opacity:"show", height:"show" },
		hoverClass	: "sfHover",
		delay		: 800,
		animation	: {opacity:"show"},
		speed		: "normal",
		oldJquery	: false, // set to true if using jQuery version below 1.2 
		disableHI	: false /*, // set to true to disable hoverIntent detection
		pathClass	: "overideThisToUse",
		onInit		: function(){},
		onBeforeShow: function(){},
		onShow		: function(){},
		onHide		: function(){}
*/	});


	// drag & drop that will extend over multiple refreshes (for Queue)
	$('#queueTable').livequery(function() {
		
		InitiateDragAndDrop(); // also called when queue is manually refreshed

		// skip queue refresh on mouseover
		$('#queueTable').bind("mouseover", function(){ skipRefresh=true; });
		$('#queueTable').bind("mouseout", function(){ skipRefresh=false; });
		$('.box_fatbottom').bind("mouseover mouseout", function(){ skipRefresh=false; });
    });
	

	// tooltips that will extend over multiple refreshes (for History)
	$('#history div').livequery(function() {
        $(this).Tooltip({
	    	extraClass: "tooltip",
	    	track: true, 
			fixPNG: true
		});
    });

	
	/* // more tooltip options
	$(".queue_delete").tooltip({ 
	    track: true, 
	    delay: 0, 
	    showURL: false, 
	    showBody: " - ", 
	    opacity: 0.85 
	});
	$("#fancy, #fancy2").tooltip({ 
    track: true, 
    delay: 0, 
    showURL: false, 
    opacity: 1, 
    fixPNG: true, 
    showBody: " - ", 
    extraClass: "pretty fancy", 
    top: -15, 
    left: 5 
	}); 
	 $('#pretty').tooltip({ 
	    track: true, 
	    delay: 0, 
	    showURL: false, 
	    showBody: " - ", 
	    extraClass: "pretty", 
	    fixPNG: true, 
	    opacity: 0.95, 
	    left: -120 
	});
	$('#right a').tooltip({ 
	    track: true, 
	    delay: 0, 
	    showURL: false, 
	    extraClass: "right" 
	}); 
	$('#right2 a').tooltip({ showURL: false });
	*/


	// restore Add NZB from cookie
	if (ReadCookie('Plush2AddNZB') == 'block')
		$('#add_nzb_menu').css('display','block');

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
	
	// "On Queue Finish" main menu item menu select
	$("#onQueueFinish-option").change( function() {
		$.ajax({
			type: "GET",
			url: "queue/change_queue_complete_action?action="+$("#onQueueFinish-option").val()+"&dummy="+Math.random()
		});
	});


	// auto show/hide of extra queue options
	$('#hdr-queue').bind("mouseover mouseout", function(){
		$('.q_menu_sort').toggleClass("show");
		//$('.q_menu_purge').toggleClass("show");
	});
	$('.box_banner_history').bind("mouseover mouseout", function(){
		$('.h_menu_purge').toggleClass("show");
		$('.h_menu_verbose').toggleClass("show");
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
	
	
	$('#add_nzb_menu_toggle').bind('click', function() { 
		$('#add_nzb_menu').toggle();
		SetCookie('Plush2AddNZB',$('#add_nzb_menu').css('display'));
	});
	
	
	// Set up +NZB
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

	// pause / resume
	$('#pause_resume').click(function(event) {
		if ($(event.target).attr('class') == 'q_menu_pause q_menu_paused')
			$.ajax({
				type: "GET",
				url: "queue/resume?dummy="+Math.random(),
				success: function(result){return LoadTheQueue(result);}
			});
		else
			$.ajax({
				type: "GET",
				url: "queue/pause?dummy="+Math.random(),
				success: function(result){return LoadTheQueue(result);}
			});
		$('#pause_resume').toggleClass("q_menu_paused");
	});
	
	// Set up Queue Menu actions
	$('#queue').click(function(event) {
		/*if ($(event.target).is('#queue_verbosity')) {
			$.ajax({
				type: "GET",
				url: "queue/tog_verbose?dummy="+Math.random(),
				success: function(result){
   					return LoadTheQueue(result);
				}
			});
		}
		else*/ 
		if ($(event.target).is('.queue_delete')) {
			delid = $(event.target).parent().parent().attr('id');
			$.ajax({
				type: "GET",
				url: 'queue/delete?dummy='+Math.random()+'&uid='+delid,
				success: function(result){
					$('#'+delid).fadeOut("slow", function(){$('#'+delid).remove();});
				}
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
			$.ajax({
				type: "GET",
				url: 'history/delete?dummy='+Math.random()+'&job='+delid,
				success: function(result){
					$('#'+delid).fadeOut("slow", function(){$('#'+delid).remove();});
				}
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
	if (skipRefresh) return false; // set within queue <table>
	$.ajax({
		type: "GET",
		url: 'queue/?dummy='+Math.random(),
		success: function(result){
 			return $('#queue').html(result);
		}
	});
}

// in a function since some processes need to refresh the queue outside of MainLoop()
function RefreshTheHistory() {
	//if (skipRefresh) return false; // set within queue <table>
	$.ajax({
		type: "GET",
		url: 'history/?dummy='+Math.random(),
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
    	//onDragClass: "myDragClass",
    	onDrop: function(table, row) {
           	var rows = table.tBodies[0].rows;
			
			if (rows.length < 2)
				return false;
			
			// figure out which position dropped row is at now
          	for ( var i=0; i < rows.length; i++ )
				if (rows[i].id == row.id)
					return ChangeOrder("switch?uid1="+row.id+"&uid2="+i);

			return false;
    	}
	});	
}


// change post-processing options within queue
function ChangeProcessingOption (nzo_id,op) {
	$.ajax({
		type: "GET",
		url: 'queue/change_opts?dummy='+Math.random()+'&nzo_id='+nzo_id+'&pp='+op/*,
	  	success: function(result){
   			return LoadTheQueue(result);
		}*/
	});
}

// change category within queue
function ChangeCategory (nzo_id,cat) {
	$.ajax({
		type: "GET",
		url: 'queue/change_cat?dummy='+Math.random()+'&nzo_id='+nzo_id+'&cat='+cat/*,
	  	success: function(result){
   			return LoadTheQueue(result);
		}*/
	});
}

// change post-processing options within queue
function ChangeProcessingScript (nzo_id,op) {
	$.ajax({
		type: "GET",
		url: 'queue/change_script?dummy='+Math.random()+'&nzo_id='+nzo_id+'&script='+op/*,
	  	success: function(result){
   			return LoadTheQueue(result);
		}*/
	});
}

// change queue order
// ex. ChangeOrder("switch?uid1="+row.id+"&uid2="+i);
function ChangeOrder (result) {
	$.ajax({
		type: "GET",
		url: "queue/"+result+"&dummy="+Math.random()/*,
	  	success: function(result){
   			return LoadTheQueue(result);
		}*/
	});
}

/*
// queue verbosity re-order arrows top/up/down/bottom
function ManipNZF (nzo_id, nzf_id, action) {
	if (action == 'Drop') {
		$.ajax({
			type: "GET",
			url: "queue/removeNzf",
			data: "nzo_id="+nzo_id+"&nzf_id="+nzf_id+"&dummy="+Math.random(),
			success: function(result){ // nzo page
   				return RefreshTheQueue()
			}
		});
	} else {	// moving top/up/down/bottom (delete is above)
		$.ajax({
			type: "GET",
			url: 'queue/'+nzo_id+'/bulk_operation',
			data: nzf_id + '=on' + '&' + 'action_key=' + action,
			success: function(result){ // nzo page
   				return RefreshTheQueue();
			}
		});
	}
}
*/

// ajax file upload
function startCallback() {
    // make something useful before submit (onStart)
    return true;
}
// ajax file upload
function completeCallback(result) {
    // make something useful after (onComplete)
	return RefreshTheQueue();
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

