
var refreshRate = 5; // default

// once the DOM is ready, run this
$(document).ready(function() {
	// refresh rate
	if (ReadCookie('PlushRefresh')) {
		refreshRate = ReadCookie('PlushRefresh');
	} else {
		SetCookie('PlushRefresh',refreshRate);	
	}
	$("#refreshRate-option").val(refreshRate);

	// Queue & History layout restoration
	if ('sidebyside' == ReadCookie('PlushLayout')) {
		$("#queue").addClass("queue_sidebyside");
		$("#history").addClass("history_sidebyside");
	}

	// Queue & History layout togglers
	$('#layout_sidebyside').bind('click', function() { 
		$("#queue").addClass("queue_sidebyside");
		$("#history").addClass("history_sidebyside");
		SetCookie('PlushLayout','sidebyside');
	});
	$('#layout_toptobottom').bind('click', function() { 
		$("#queue").removeClass("queue_sidebyside");
		$("#history").removeClass("history_sidebyside");
		SetCookie('PlushLayout','toptobottom');
	});
	
	// Set up lightbox floating window
	$("a.greybox").click(function(){
		var t = this.title || this.innerHTML || this.href;
		GB_show(t,this.href,500,700);
		return false;
    });
	// Set up Main Menu actions
	$('#options').bind('click', function() { 
		$('#options').toggleClass('on');
		$('#optionsMenu').toggle();
	});
	$('#plusnzb').bind('click', function() { 
		$('#plusnzb').toggleClass('on');
		$('#nzbMenu').toggle();
	});

	var myOptions = {
		min: 1,						// Set lower limit.
		max: 100,					// Set upper limit.
		step: 1,					// Set increment size.
		spinClass: 'spin-button',	// CSS class to style the spinbutton. (Class also specifies url of the up/down button image.)
		upClass: 'spin-up',			// CSS class for style when mouse over up button.
		downClass: 'spin-down'		// CSS class for style when mouse over down button.
	}
	$("#refreshRate-option").SpinButton(myOptions);
	$("#refreshRate-option").change( function() { 
		refreshRate = $("#refreshRate-option").val();
		SetCookie('PlushRefresh',refreshRate);
	 });
	$("#refreshRate-option").click( function() { 
		refreshRate = $("#refreshRate-option").val();
		SetCookie('PlushRefresh',refreshRate);
	 });

		
	// Set up +NZB
	$('#addNZBbyID').bind('click', function() { 
		$.ajax({
			type: "GET",
			url: "addID",
			data: "id="+$("#addID").val()+"&pp="+$("#addID_pp").val()+"&script="+$("#addID_script").val(),
			success: function(result){
   				return RefreshTheQueue();
			}
		});
		$("#addID").val('by Newzbin ID/NB32');
	});
	$('#addNZBbyURL').bind('click', function() { 
		$.ajax({
			type: "GET",
			url: "addURL",
			data: "url="+$("#addURL").val()+"&pp="+$("#addURL_pp").val()+"&script="+$("#addURL_script").val(),
			success: function(result){
   				return RefreshTheQueue();
			}
		});
		$("#addURL").val('by URL');
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
	
	
	// Set up Queue Menu actions
	$('#queue').click(function(event) {
		if ($(event.target).is('#pause_resume')) {
			if ($(event.target).attr('class') == 'active')
				$.ajax({
					type: "GET",
					url: "queue/resume?dummy="+Math.random(),
					success: function(result){
   						return LoadTheQueue(result);
					}
				});
			else
				$.ajax({
					type: "GET",
					url: "queue/pause?dummy="+Math.random(),
					success: function(result){
   						return LoadTheQueue(result);
					}
				});
		}
		else if ($(event.target).is('#queue_verbosity')) {
			$.ajax({
				type: "GET",
				url: "queue/tog_verbose?dummy="+Math.random(),
				success: function(result){
   					return LoadTheQueue(result);
				}
			});
		}
		else if ($(event.target).is('#queue_sortage')) {
			$.ajax({
				type: "GET",
				url: "queue/sort_by_avg_age?dummy="+Math.random(),
				success: function(result){
   					return LoadTheQueue(result);
				}
			});
		}
		else if ($(event.target).is('#queue_sortname')) {
			$.ajax({
				type: "GET",
				url: "queue/sort_by_name?dummy="+Math.random(),
				success: function(result){
   					return LoadTheQueue(result);
				}
			});
		}
		else if ($(event.target).is('#queue_shutdown')) {
			$.ajax({
				type: "GET",
				url: "queue/tog_shutdown?dummy="+Math.random(),
				success: function(result){
   					return LoadTheQueue(result);
				}
			});
		}
		else if ($(event.target).is('.btnDeleteQueue')) {
			$.ajax({
				type: "GET",
				url: 'queue/delete?dummy='+Math.random()+'&uid='+$(event.target).parent().parent().attr('id'),
				success: function(result){
   					return LoadTheQueue(result);
				}
			});
		}
	});
	
	
	// Set up History Menu actions
	$('#history').click(function(event) {
		if ($(event.target).is('#history_verbosity')) {
			$('#history').load('history/tog_verbose?dummy='+Math.random());
		}
		else if ($(event.target).is('#history_purge')) {
			$('#history').load('history/purge?dummy='+Math.random());
		}
		else if ($(event.target).is('.btnDeleteHistory')) {
			$.ajax({
				type: "GET",
				url: 'history/delete?dummy='+Math.random()+'&job='+$(event.target).parent().parent().attr('id'),
				success: function(result){
   					return $('#history').html(result);
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
	$('#history').load('history?dummy='+Math.random());

	// loop
	setTimeout("MainLoop()",refreshRate*1000);
}

// in a function since some processes need to refresh the queue outside of MainLoop()
function RefreshTheQueue() {
	$('#queue').load('queue?dummy='+Math.random() , function(){
		document.title = 'SAB+ '+$('#stats_kbpersec').html()+' KB/s '+$('#stats_eta').html()+' left of '+$('#stats_noofslots').html();
		InitiateDragAndDrop();
	});
}

// refresh the queue with supplied data (like if we already made an AJAX call)
function LoadTheQueue(result) {
	$('#queue').html(result);
	document.title = 'SAB+ '+$('#stats_kbpersec').html()+' KB/s '+$('#stats_eta').html()+' left of '+$('#stats_noofslots').html();
	InitiateDragAndDrop();
}

var rowsBeforeDragAndDrop;

// called upon every refresh
function InitiateDragAndDrop() {

   	rowsBeforeDragAndDrop = $('#queueContent').children();

	$("#queueTable").tableDnD({
    	//onDragClass: "myDragClass",
    	onDrop: function(table, row) {
           	var rows = table.tBodies[0].rows;
			var droppedon = "";
			
			if (rows.length < 2)
				return false;
			
			// dragged to the top, replaced the first one
			if (rows[0].id == row.id && row.id != rowsBeforeDragAndDrop[0].id)
				droppedon = rows[1].id;
				
			// dragged to the bottom, replaced the last one
			else if (rows[rows.length-1].id == row.id && row.id != rowsBeforeDragAndDrop[rowsBeforeDragAndDrop.length-1].id)	
				droppedon = rows[rows.length-2].id;
				
			// search for where it was dropped on
			else if ( rows.length > 2 ) {
           		for ( var i=1; i < rows.length-1; i++ ) {
					if ( rows[i].id == row.id  && rows[i-1].id == rowsBeforeDragAndDrop[i].id )
						droppedon = rows[i-1].id;
					else if ( rows[i].id == row.id  && rows[i+1].id == rowsBeforeDragAndDrop[i].id )
						droppedon = rows[i+1].id;
				}
			}
			if (droppedon!="")
				return ChangeOrder("switch?uid1="+row.id+"&uid2="+droppedon);
			return false;
    	}
	});	
}


// change post-processing options within queue
function ChangeProcessingOption (nzo_id,op) {
	$.ajax({
		type: "GET",
		url: 'queue/change_opts?dummy='+Math.random()+'&nzo_id='+nzo_id+'&pp='+op,
	  	success: function(result){
   			return LoadTheQueue(result);
		}
	});
}

// change post-processing options within queue
function ChangeProcessingScript (nzo_id,op) {
	$.ajax({
		type: "GET",
		url: 'queue/change_script?dummy='+Math.random()+'&nzo_id='+nzo_id+'&script='+op,
	  	success: function(result){
   			return LoadTheQueue(result);
		}
	});
}

// change queue order
// switch?uid1=$slot.nzo_id&uid2=$slotinfo[i].nzo_id
function ChangeOrder (result) {
	$.ajax({
		type: "GET",
		url: "queue/"+result+"&dummy="+Math.random(),
	  	success: function(result){
   			return LoadTheQueue(result);
		}
	});
}

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


// used to store layout settings
function SetCookie(name,val) {
	var date = new Date();
	date.setTime(date.getTime()+(365*24*60*60*1000));
	document.cookie = name+"="+val+"; expires="+ date.toGMTString() +"; path=/";
}

// used during initialization to restore layout settings
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
