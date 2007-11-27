// globals
var queue;							// contains parsed json
var histore;						// chokes when this is named 'history'???
var changingOrder = false;			// when you are mid-drag the container will serialize at current position; this is how NOVA knows not to redraw
var lastQueueOrder = new Array();	// know when to reset container ids (to be replaced I believe)

// queue drag & drop sort effect
var myStartEffect = function(element) { new Effect.Opacity(element, {duration:0, from:0.2, to:0.6}); }

// called upon page load -- restore previous layout & initiate data updates
window.onload=function(){
	if (ReadCookie('Layout_Orientation')=='TopToBottom')
		$("history_container").style.clear  =   $("queue_container").style.clear 	='both';
	if (ReadCookie('Layout_Stats')=='hide')		$("dataBar").style.display 			='none';	
	if (ReadCookie('Layout_Queue')=='hide')		$("queue_container").style.display  ='none';
	if (ReadCookie('Layout_History')=='hide')	$("history_container").style.display='none';	
	if (ReadCookie('RefreshRate')) {
		refreshTime = ReadCookie('RefreshRate');
		$('refresh_handle').innerHTML='<small>&nbsp;&nbsp;'+refreshTime+'&nbsp;sec</small>';
	}
	MainLoop();
}

// called every refresh (calls itself)
function MainLoop(){

	// handle queue json
	new Ajax.Request('queue', {
		method:'get',
		requestHeaders: {Accept: 'application/json'},
		onSuccess: function(transport){
			queue = transport.responseText.evalJSON();
			RefreshQueueOrder();
			// main stats
			document.title= 'NOVA ' + Math.round(queue.kbpersec) + ' KB/s '+queue.noofslots+' Queued';
			$("logo").title = "Uptime: "+queue.uptime;
			$("kbpersec").innerHTML = Math.round(queue.kbpersec);
			$("mbdone").innerHTML 	= Math.round(queue.mb-queue.mbleft);
			$("mb").innerHTML 		= Math.round(queue.mb);
			$("mbleft").innerHTML 	= Math.round(queue.mbleft/1024*100)/100;
			$("statusbar").style.width = 
			$("statusbartext").innerHTML = (queue.mb > 0) ?  Math.round((1-queue.mbleft/queue.mb)*100)+'%' : "0%";
			if ($("diskspace1").innerHTML !=queue.diskspace1)
				$("diskspace1").innerHTML = queue.diskspace1;
			if ($("diskspace2").innerHTML !=queue.diskspace2)
				$("diskspace2").innerHTML = queue.diskspace2;
			$("timeleft").innerHTML = "&nbsp;<b>"+TimeLeft(queue.kbpersec, queue.mbleft, queue.mb)+"</b>";
			if (queue.paused=='True' && $("queue_pause").innerHTML != 'Paused!') {
				$("queue_pause").innerHTML = 'Paused!';
				$("queue_pause").setAttribute("class", "toggled"); 
				$("queue_pause").setAttribute("onclick", "NOVAction('queue_resume')"); 
			} else if (queue.paused=='False' && $("queue_pause").innerHTML != 'Pause') {
				$("queue_pause").innerHTML = 'Pause';
				$("queue_pause").setAttribute("class", "untoggled"); 
				$("queue_pause").setAttribute("onclick", "NOVAction('queue_pause')"); 
			}
			if (queue.noofslots>0 && 
				( queue.jobs[0].finished.length>0
				||queue.jobs[0].active.length>0
				||queue.jobs[0].queued.length>0) && $("queue_tog_verbose").innerHTML != 'Verbosity!') {
				$("queue_tog_verbose").innerHTML = 'Verbosity!';
				$("queue_tog_verbose").setAttribute("class", "toggled"); 
			} else if (queue.noofslots>0 && 
				( queue.jobs[0].finished.length==0
				&&queue.jobs[0].active.length==0
				&&queue.jobs[0].queued.length==0) && $("queue_tog_verbose").innerHTML != 'Verbosity') {
				$("queue_tog_verbose").innerHTML = 'Verbosity';
				$("queue_tog_verbose").setAttribute("class", "untoggled"); 
			}
			if (queue.shutdown=='True' && $("queue_tog_shutdown").innerHTML != 'Shutdown!') {
				$("queue_tog_shutdown").innerHTML = 'Shutdown!';
				$("queue_tog_shutdown").setAttribute("class", "toggled"); 
			} else if (queue.shutdown=='False' && $("queue_tog_shutdown") && $("queue_tog_shutdown").innerHTML != 'Shutdown') {
				$("queue_tog_shutdown").innerHTML = 'Shutdown';
				$("queue_tog_shutdown").setAttribute("class", "untoggled"); 
			}
			for(var i=0; i<queue.noofslots; i++) {
				var nzb = $(queue.jobs[i].nzo_id);
				//filename
				var goodname = queue.jobs[i].filename;
				var hop = "";
				if (queue.jobs[i].msgid!='') {
					// newzbin name spruceage
					hop = "https://v3.newzbin.com/browse/post/"+queue.jobs[i].msgid;
				}
				// filename
				if (nzb.childNodes[0].childNodes[1].innerHTML != goodname) {
					nzb.childNodes[0].childNodes[1].innerHTML  	= goodname;
					nzb.childNodes[0].childNodes[1].title 	 	= queue.jobs[i].filename;
				}
				// progress bar
				nzb.childNodes[1].childNodes[0].childNodes[0].style.width = Math.round((1-queue.jobs[i].mbleft/queue.jobs[i].mb)*100)+'%';
				// MB downloaded
				nzb.childNodes[1].childNodes[4].innerHTML = '&nbsp;<b><span>'+Math.round(queue.jobs[i].mb - queue.jobs[i].mbleft)+'</span></b><small> of </small><b>'+Math.round(queue.jobs[i].mb)+'</b><small> MB</small>';
				// time left
				nzb.childNodes[1].childNodes[1].innerHTML = "&nbsp;<b>"+TimeLeft(queue.kbpersec, queue.jobs[i].mbleft, queue.jobs[i].mb)+"</b>";	
				nzb.childNodes[1].title 	= "ETA: "+queue.jobs[i].eta+" ... Average Age: "+queue.jobs[i].avg_age;
				// hop
				if (hop!="" && nzb.childNodes[2].childNodes[1].href != hop) {
					nzb.childNodes[2].childNodes[1].href 		= hop;
					nzb.childNodes[2].childNodes[1].target 		= "_blank";
					nzb.childNodes[2].childNodes[1].childNodes[0].src = 'static/images/icon-newzbin.png';
				}
				// post-processing options
				nzb.childNodes[2].childNodes[2].selectedIndex 	= queue.jobs[i].unpackopts;
				// verbosity
				if ($("queue_tog_verbose").innerHTML == 'Verbosity!' && nzb.childNodes[0].childNodes[2].style.display != 'none') {
					var verbosity_names='';
					var verbosity_sizes='';
					var verbosity_icons='';
					// finished files
					verbosity_names = '<font color="green"><br/><i>.: <u>Finished</u></i><br/>';
					verbosity_sizes = '<font color="green"><br/>';
					verbosity_icons = '<br/><br/>';
					for (var j=0; j<queue.jobs[i].finished.length; j++) {
						verbosity_names += '<span title="Age: '+queue.jobs[i].finished[j].age+'">'+queue.jobs[i].finished[j].filename+'</span><br/>';
						verbosity_sizes += Math.round((queue.jobs[i].finished[j].mb - queue.jobs[i].finished[j].mbleft)*100)/100 +' of '+ queue.jobs[i].finished[j].mb +' MB<br/>';
						verbosity_icons += '<br/>';
					}
					// active files
					verbosity_names += '</font><font color="red"><i>.: <u>Active</u></i><br/>';
					verbosity_sizes += '</font><font color="red"><br/>';
					verbosity_icons += '<br/>';
					for (var j=0; j<queue.jobs[i].active.length; j++) {
						verbosity_names += '<span title="File Age: '+queue.jobs[i].active[j].age+'">'+queue.jobs[i].active[j].filename+'</span><br/>';
						verbosity_sizes += Math.round((queue.jobs[i].active[j].mb - queue.jobs[i].active[j].mbleft)*100)/100 +' of '+ queue.jobs[i].active[j].mb +' MB<br/>';
						verbosity_icons += '<span id="'+queue.jobs[i].active[j].nzf_id+'">'
						+'<a title="Move to Top" style="cursor: pointer" onClick="MoveNZF(this.parentNode.parentNode.parentNode.parentNode.id,this.parentNode.id,\'Top\');"> '
							+'<img width="12" height="12" src="static/images/icon-queue-2uparrow.png" border="0" /></a>&nbsp;'
						+'<a title="Move Up" style="cursor: pointer" onClick="MoveNZF(this.parentNode.parentNode.parentNode.parentNode.id,this.parentNode.id,\'Up\');"> '
							+'<img width="12" height="12" src="static/images/icon-queue-1uparrow.png" border="0" /></a>&nbsp;'
						+'<a title="Move Down" style="cursor: pointer" onClick="MoveNZF(this.parentNode.parentNode.parentNode.parentNode.id,this.parentNode.id,\'Down\');"> '
							+'<img width="12" height="12" src="static/images/icon-queue-1downarrow.png" border="0" /></a>&nbsp;'
						+'<a title="Move to Bottom" style="cursor: pointer" onClick="MoveNZF(this.parentNode.parentNode.parentNode.parentNode.id,this.parentNode.id,\'Bottom\');"> '
							+'<img width="12" height="12" src="static/images/icon-queue-2downarrow.png" border="0" /></a>&nbsp;'
						+'<a title="Drop File" style="cursor: pointer" onClick="DropNZF(this.parentNode.parentNode.parentNode.parentNode.id,this.parentNode.id);"> '
							+'<img width="12" height="12" src="static/images/icon-queue-drop.png" border="0" /></a>'
						+'</span><br/>';
					}
					// queued files
					verbosity_names += '</font><font color="blue"><i>.: <u>Queued</u></i><br/>';
					verbosity_sizes += '</font><font color="blue"><br/>';
					verbosity_icons += '<br/>';
					for (var j=0; j<queue.jobs[i].queued.length; j++) {
						verbosity_names += '<span title="Age: '+queue.jobs[i].queued[j].age+' ... Set: '+queue.jobs[i].queued[j].set+'">'+queue.jobs[i].queued[j].filename+'</span><br/>';
						verbosity_sizes += Math.round((queue.jobs[i].queued[j].mb - queue.jobs[i].queued[j].mbleft)*100)/100 +' of '+ queue.jobs[i].queued[j].mb +' MB<br/>';
						verbosity_icons += '<br/>';
					}
					verbosity_names += '</font>';
					verbosity_sizes += '</font>';
					// and update 
					if (nzb.childNodes[0].childNodes[2].innerHTML !=verbosity_names)
						nzb.childNodes[0].childNodes[2].innerHTML = verbosity_names;
					if (nzb.childNodes[1].childNodes[5].innerHTML !=verbosity_sizes)
						nzb.childNodes[1].childNodes[5].innerHTML = verbosity_sizes;
					if (nzb.childNodes[2].childNodes[4].innerHTML !=verbosity_icons)
						nzb.childNodes[2].childNodes[4].innerHTML = verbosity_icons;
				}
				
			}}});

			// handle history json
			new Ajax.Request('history', {
				method:'get',
				requestHeaders: {Accept: 'application/json'},
				onSuccess: function(transport){
					histore = transport.responseText.evalJSON(); // it didnt work when i called it 'history'
					$("bytes_beginning").innerHTML = histore.bytes_beginning;	// main stats
					$("total_bytes").innerHTML = histore.total_bytes;			// main stats
					if (histore.lines.length>0 && 
							histore.lines[0].stages.length>0 && $("history_tog_verbose").innerHTML != 'Verbosity!') {
						$("history_tog_verbose").innerHTML = 'Verbosity!';
						$("history_tog_verbose").setAttribute("class", "toggled"); 
					} else if (	histore.lines.length>0 && 
							histore.lines[0].stages.length==0 && $("history_tog_verbose").innerHTML != 'Verbosity!') {
						$("history_tog_verbose").innerHTML = 'Verbosity';
						$("history_tog_verbose").setAttribute("class", "untoggled"); 
					}
					var numnodes = $("history").getElementsByTagName("tr").length;
					var nzb;
					var verbosity;
					while (numnodes<histore.lines.length) {			// need more node(s)
						$("history").insert('<tr class="odd"><td class="textLeft"></td></tr>');
						numnodes++;
					}
					while (numnodes-->histore.lines.length) 		// need less node(s)
						$("history").removeChild($("history").lastChild);
					for (var i=0; i<histore.lines.length; i++) {	// make updates
						var hop = "";
						var loading = "";
						var sick = "";
						var goodname = histore.lines[i].filename;
						if (histore.lines[i].msgid!="") {
							hop = '<a href="https://v3.newzbin.com/browse/post/' + histore.lines[i].msgid+'" style="cursor: pointer" title="View Report" id="hop" target="_blank"><img src="static/images/icon-newzbin.png" width="15" height="17" style="float: right" alt="^N " border="0"/></a>';
						}
						if (histore.lines[i].loaded=="True")
							loading = '<img src="static/images/icon-history-postprocessing.gif" title="Post-processing nzb now..." width="16" height="16" style="float: right" alt="... " border="0"/>';
						// verbosity
						if (histore.lines[i].stages.length>0) {
							verbosity='<br/>';
							for (var j=0; j<histore.lines[i].stages.length; j++) {
								for (var k=0; k<histore.lines[i].stages[j].actions.length; k++) {
									switch (histore.lines[i].stages[j].actions[k].name.substr(1,3)) {
										case "PAR":
											verbosity += '<img src="static/images/icon-history-par2.png" title="'+histore.lines[i].stages[j].actions[k].value.substr(3)+' :: '+histore.lines[i].stages[j].actions[k].name+'" />';
											break;
										case "RAR":
											verbosity += '<img src="static/images/icon-history-unrar.png" title="'+histore.lines[i].stages[j].actions[k].value.substr(3)+' :: '+histore.lines[i].stages[j].actions[k].name+'" />';
											break;
										case "ZIP":
											verbosity += '<img src="static/images/icon-history-unzip.gif" title="'+histore.lines[i].stages[j].actions[k].value.substr(3)+' :: '+histore.lines[i].stages[j].actions[k].name+'" />';
											break;
										case "DEL":
											verbosity += '<img src="static/images/icon-history-cleanup.png" title="'+histore.lines[i].stages[j].actions[k].value.substr(3)+' :: '+histore.lines[i].stages[j].actions[k].name+'" />';
											break;
										case "FJN":
											verbosity += '<img src="static/images/icon-history-join.png" title="'+histore.lines[i].stages[j].actions[k].value.substr(3)+' :: '+histore.lines[i].stages[j].actions[k].name+'" />';
											break;
										default:
											verbosity += '<i title="'+histore.lines[i].stages[j].actions[k].value.substr(3)+' :: '+histore.lines[i].stages[j].actions[k].name+'" />['+ histore.lines[i].stages[j].actions[k].name.substr(1,3) +']</i>';
									};
									switch (histore.lines[i].stages[j].actions[k].value.substr(3,8)) {
										case 'Scanning':
										case 'Verified':
										case 'Repaired':
										case 'Unpacked':
										case 'Unzipped':
										case 'Deleted ':
											break; // clean verbosity
										default:
											verbosity += '<sup><small style="color:blue">&nbsp;'+ histore.lines[i].stages[j].actions[k].value.substr(3) +'</small></sup>';
											break;
									};
									if (histore.lines[i].stages[j].actions[k].value.substr(0,9) == "=> ERROR:" || histore.lines[i].stages[j].actions[k].value.substr(0,6) == "=> Not")
										sick = '<img src="static/images/icon-history-fucked.png" title="Broken nzb set detected!!" width="16" height="16" style="float: right" alt="... " border="0"/>';
								}
							}
						} else verbosity='';
						if ($("history").childNodes[i].childNodes[0].innerHTML !=hop+loading+sick+'<strong style="margin-right: 20px; cursor:default">'+goodname+'</strong>'+verbosity) {
							$("history").childNodes[i].childNodes[0].innerHTML = hop+loading+sick+'<strong style="margin-right: 20px; cursor:default">'+goodname+'</strong>'+verbosity;
							$("history").childNodes[i].title 	 = 'Done @ '+histore.lines[i].added+' :: '+histore.lines[i].filename;
						}
					}
				}});

	setTimeout("MainLoop()",refreshTime*1000); // loop
}

// determine time left in HH:MM:SS
// replace this with parsed ETA for queued items
// will still be necessary for overall ETA
function TimeLeft (kbpersec, mbleft, mb) { 
	var timeleft = '&infin;';
	if (kbpersec >= 1 && mb > 0) {
		var kbleft = mbleft * 1024;
		var hoursleft = 0;
		var minsleft = 0;
		var secsleft = Math.round(kbleft / kbpersec);
		if (secsleft>=60) {
			minsleft = Math.round(secsleft/60);
			secsleft = secsleft%60;
		}
		if (minsleft>=60) {
			hoursleft = Math.round(minsleft/60);
			minsleft = minsleft%60;
		}
		timeleft  = ((hoursleft < 10) ?  "0" : "") + hoursleft;
		timeleft += ((minsleft  < 10) ? ":0" : ":") + minsleft;
		timeleft += ((secsleft  < 10) ? ":0" : ":") + secsleft;
	}
	return timeleft;
}

// append an empty enqueued nzb container
function AppendNZBSlot(nzo_id) {
	
	if (sabplus=='F')	// 0.2.5
	$("queue").insert('<tr class="odd" id="'+nzo_id+'">'
						+'<td class="handle" ondblclick="JumpTopOfQueue(this.parentNode.id)" style="cursor:move">'
							+'<img src="static/images/icon-queue-order.png" alt=": " title="Drag &amp; Drop to Sort" style="float:left; padding-top:2px;" height="11" /><strong></strong><div style="display:none"></div>'
						+'</td><td width="200px">'
							+'<div class="queueBarOuter"><div class="queueBarInner" style="width: 0.0%;"></div></div><span style="float: right"></span><img title="Time Left (HH:MM:SS)" width="14" height="14" style="float: right" src="static/images/icon-header-timeleft.png" /><img title="Megabytes Remaining" width="14" height="14" style="float: left" src="static/images/icon-header-mbleft.png" /><span title="Megabytes Remaining"></span><div style="display:none"></div>'
						+'</td><td>'
							+'<img title="Show Files (Waits until next refresh cycle) (Verbosity must be toggled -on-)" onClick="ShowVerbosity(this.parentNode.parentNode.id)" width="16" height="16" src="static/images/icon-queue-1downarrow.png" border="0" style="cursor:pointer; margin-right: 4px; margin-top: 4px"/>'
							+'<a target="" title="View Report" style="cursor: pointer;margin-right: 8px;margin-left: 4px;"><img src="static/images/icon-blank.png" width="15" height="17" border="0" /></a>'
							+'<select title="Post-Processing" onchange="ChangeProcessingOption(this.parentNode.parentNode.id,this.selectedIndex);" style="color:#FFF;background-color:#2E76D3;margin-bottom: 4px">'
								+'<option value="0" title="Do not post-process the NZB file set">-</option>'
								+'<option value="1" title="Repair the NZB file set with PAR2 files">R</option>'
								+'<option value="2" title="Repair &amp; Unpack the NZB file set">U</option>'
								+'<option value="3" title="Repair, Unpack, &amp; Delete the unneeded remainder of the NZB file set">D</option>'
							+'</select>'
							+'<img title="Drop NZB" onClick="DropNZB(this.parentNode.parentNode.id);" width="16" height="16" src="static/images/icon-queue-drop.png" border="0" style="cursor:pointer; margin-left: 8px; margin-top: 4px"/>'
							+'<div style="display:none"></div>'
						+'</td></tr>');
	else				// 0.2.7+
	$("queue").insert('<tr class="odd" id="'+nzo_id+'">'
						+'<td class="handle" ondblclick="JumpTopOfQueue(this.parentNode.id)" style="cursor:move">'
							+'<img src="static/images/icon-queue-order.png" alt=": " title="Drag &amp; Drop to Sort" style="float:left; padding-top:2px;" height="11" /><strong></strong><div style="display:none"></div>'
						+'</td><td width="200px">'
							+'<div class="queueBarOuter"><div class="queueBarInner" style="width: 0.0%;"></div></div><span style="float: right"></span><img title="Time Left (HH:MM:SS)" width="14" height="14" style="float: right" src="static/images/icon-header-timeleft.png" /><img title="Megabytes Remaining" width="14" height="14" style="float: left" src="static/images/icon-header-mbleft.png" /><span title="Megabytes Remaining"></span><div style="display:none"></div>'
						+'</td><td>'
							+'<img title="Show Files (Waits until next refresh cycle) (Verbosity must be toggled -on-)" onClick="ShowVerbosity(this.parentNode.parentNode.id)" width="16" height="16" src="static/images/icon-queue-1downarrow.png" border="0" style="cursor:pointer; margin-right: 4px; margin-top: 4px"/>'
							+'<a target="" title="View Report" style="cursor: pointer;margin-right: 8px;margin-left: 4px;"><img src="static/images/icon-blank.png" width="15" height="17" border="0" /></a>'
							+'<select title="Post-Processing" onchange="ChangeProcessingOption(this.parentNode.parentNode.id,this.selectedIndex);" style="color:#FFF;background-color:#2E76D3;margin-bottom: 4px">'
								+'<option value="0" title="Do not post-process the NZB file set">-</option>'
								+'<option value="1" title="Repair the NZB file set with PAR2 files">R</option>'
								+'<option value="2" title="Repair &amp; Unpack the NZB file set">U</option>'
								+'<option value="3" title="Repair, Unpack, &amp; Delete the unneeded remainder of the NZB file set">D</option>'
								+'<option value="4" title="(+Script) Repair, Unpack, &amp; Delete the remainder of the NZB file set">R+</option>'
					            +'<option value="5" title="(+Script) Repair, Unpack, &amp; Delete the remainder of the NZB file set">U+</option>'
					            +'<option value="6" title="(+Script) Repair, Unpack, &amp; Delete the remainder of the NZB file set" selected>D+</option>'
							+'</select>'
							+'<img title="Drop NZB" onClick="DropNZB(this.parentNode.parentNode.id);" width="16" height="16" src="static/images/icon-queue-drop.png" border="0" style="cursor:pointer; margin-left: 8px; margin-top: 4px"/>'
							+'<div style="display:none"></div>'
						+'</td></tr>');
}

// called from MainLoop, resets node ids & appends/removes rows
function RefreshQueueOrder() {
	if (changingOrder)
		return false;
	var numnodes = $("queue").getElementsByTagName("tr").length;
	while (numnodes<queue.noofslots) 		// need more node(s)
		AppendNZBSlot(queue.jobs[numnodes++].nzo_id);
	while (numnodes-->queue.noofslots) 		// need less node(s)
		$("queue").removeChild($("queue").lastChild);
	var orderedNodes = $("queue").getElementsByTagName("tr");
	for (var i=0; i<queue.noofslots; i++) 	// check for updated order
		if (orderedNodes[i].getAttribute('id') != queue.jobs[i].nzo_id)
			$("queue").childNodes[i].setAttribute('id',queue.jobs[i].nzo_id);
	StoreQueueOrder();
	Sortable.create('queue', {starteffect: myStartEffect, tag:'tr',handle: 'handle',onUpdate: SortUpdate, onChange: SortChange});
	return false;
}

// so we know original order before sorting
function StoreQueueOrder() {
	var orderedNodes = $("queue").getElementsByTagName("tr");
	var currQueueOrder = new Array();
	for (var i=0;i < orderedNodes.length;i++) 
		if (orderedNodes[i].getAttribute('id') != null)
			currQueueOrder.push(orderedNodes[i].getAttribute('id'));
	lastQueueOrder = currQueueOrder;
}

// trigger called when queue sort starts
function SortChange() {
	changingOrder = true;
}

// called after a queue sort
function SortUpdate() {
	var newQueueOrder = new Array();
	var orderedNodes = $("queue").getElementsByTagName("tr");
	for (var i=0;i < orderedNodes.length;i++) 
		if (orderedNodes[i].getAttribute('id') != null)
			newQueueOrder.push(orderedNodes[i].getAttribute('id'));
	var moved_nzo_id;
	var replaced_nzo_id;
	var found=false;
	// figure out what moved where
	for (var i=0 ; !found && i < orderedNodes.length-1; i++) {
		if (lastQueueOrder[i] != newQueueOrder[i]) {
			if (lastQueueOrder[i] == newQueueOrder[i+1]) {  // typical 'move up'
				moved_nzo_id = newQueueOrder[i];
				replaced_nzo_id = lastQueueOrder[i];
				found = true;
			} else {										// possible 'move down'
				var j = i;
				while ( lastQueueOrder[i] != newQueueOrder[++j] &&	j < orderedNodes.length );
				moved_nzo_id = lastQueueOrder[i];
				replaced_nzo_id = lastQueueOrder[j];
				found = true;
			}
		}
	}
	if (found)	// make the move
		new Ajax.Request('queue/switch', {
			method: 	'get',
			parameters: {uid1: moved_nzo_id, 
						 uid2: replaced_nzo_id} });
	StoreQueueOrder();
	changingOrder = false;
	return false;
}

// slew of simple methods
function NOVAction(which) {
	switch(which) {
		case 'history_purge': 
			new Ajax.Request('history/purge',{method:'get'}); $("history").innerHTML=""; 
			break;
		case 'history_verbosity': 
			new Ajax.Request('history/tog_verbose',{method:'get'});
			if ($("history_tog_verbose").innerHTML != 'Verbosity!') {
				$("history_tog_verbose").innerHTML = 'Verbosity!';
				$("history_tog_verbose").setAttribute("class", "toggled"); 
			} else {
				$("history_tog_verbose").innerHTML = 'Verbosity';
				$("history_tog_verbose").setAttribute("class", "untoggled"); 
			}
			break;
		case 'queue_pause': 
			new Ajax.Request('queue/pause',{method:'get'});
			$("queue_pause").innerHTML = 'Paused!';
			$("queue_pause").setAttribute("class", "toggled"); 
			$("queue_pause").setAttribute("onclick", "NOVAction('queue_resume')"); 
			break;
		case 'queue_resume': 
			new Ajax.Request('queue/resume',{method:'get'});
			$("queue_pause").innerHTML = 'Pause';
			$("queue_pause").setAttribute("class", "untoggled"); 
			$("queue_pause").setAttribute("onclick", "NOVAction('queue_pause')"); 
			break;
		case 'queue_sort_by_avg_age': 
			new Ajax.Request('queue/sort_by_avg_age',{method:'get'});
			break;
		case 'queue_tog_verbose': 
			new Ajax.Request('queue/tog_verbose',{method:'get'});
			if ($("queue_tog_verbose").innerHTML != 'Verbosity!') {
				$("queue_tog_verbose").innerHTML = 'Verbosity!';
				$("queue_tog_verbose").setAttribute("class", "toggled"); 
			} else {
				$("queue_tog_verbose").innerHTML = 'Verbosity';
				$("queue_tog_verbose").setAttribute("class", "untoggled"); 
			}
			break;
		case 'queue_tog_shutdown': // windows only, not actually used because it won't post-process correctly through SABnzbd, it works in NOVA though
			if ($("queue_tog_shutdown").innerHTML != 'Shutdown!') {
				if (confirm("Are you sure you want to shut down YOUR COMPUTER upon queue completion?\nSABnzbd probably won't post-process your last downloaded nzb correctly!")) {
					new Ajax.Request('queue/tog_shutdown',{method:'get'});
					$("queue_tog_shutdown").innerHTML = 'Shutdown!';
					$("queue_tog_shutdown").setAttribute("class", "toggled"); 
				}
			} else {
				new Ajax.Request('queue/tog_shutdown',{method:'get'});
				$("queue_tog_shutdown").innerHTML = 'Shutdown';
				$("queue_tog_shutdown").setAttribute("class", "untoggled"); 
			}
			break;
		case 'shutdown': // windows only, not actually used because it won't post-process correctly through SABnzbd, it works in NOVA though
			if (confirm("Are you sure you want to shut down the SABnzbd application?"))
				window.location = 'shutdown';
			break;
		case 'addID': //+nzb
			new Ajax.Request('addID',{method:'get',
				parameters: {'id': $("addID").value, 'pp': $("addID_pp").value}});
			$("addID").value='by Report ID';
			Effect.Pulsate('plusnzb');
			Effect.toggle('2ndbar','blind');
			break;
		case 'addURL': //+nzb
			new Ajax.Request('addURL',{method:'get',
				parameters: {'url': $("addURL").value, 'pp': $("addURL_pp").value}});
			$("addURL").value='by URL';
			Effect.Pulsate('plusnzb');
			Effect.toggle('2ndbar','blind');
			break;
		case 'Layout_SideBySide':
			$("history_container").style.clear='right';
			$("queue_container").style.clear='right';
			SetCookie("Layout_Orientation","SideBySide");
			break;
		case 'Layout_TopToBottom':
			$("history_container").style.clear='both';
			$("queue_container").style.clear='both';
			SetCookie("Layout_Orientation","TopToBottom");
			break;
		case 'Layout_Queue':
			if ($("queue_container").visible()) 
				SetCookie("Layout_Queue","hide"); // about to be invis
			else
				SetCookie("Layout_Queue","show");
			Effect.toggle('queue_container','appear');
			break;
		case 'Layout_History':
			if ($("history_container").visible()) 
				SetCookie("Layout_History","hide"); // about to be invis
			else
				SetCookie("Layout_History","show");
			Effect.toggle('history_container','appear');
			break;
		case 'Layout_Stats':
			if ($("dataBar").visible()) 
				SetCookie("Layout_Stats","hide"); // about to be invis
			else
				SetCookie("Layout_Stats","show");
			Effect.toggle('dataBar','appear');
			break;
		case 'StoreRefreshRate':
			SetCookie("RefreshRate",refreshTime);
			break;
	}; return false;
}

function ShowVerbosity(id) {
	if ($(id).childNodes[0].childNodes[2].style.display=='none') {
		$(id).childNodes[0].childNodes[2].style.display = 'block';
		$(id).childNodes[1].childNodes[5].style.display = 'block';
		$(id).childNodes[2].childNodes[4].style.display = 'block';
		$(id).childNodes[2].childNodes[0].src = 'static/images/icon-queue-1uparrow.png';
	} else {
		$(id).childNodes[0].childNodes[2].style.display = 'none';
		$(id).childNodes[1].childNodes[5].style.display = 'none';
		$(id).childNodes[2].childNodes[4].style.display = 'none';
		$(id).childNodes[2].childNodes[0].src = 'static/images/icon-queue-1downarrow.png';
	}
}

// jump nzb to top of queue, called upon filename double-click
function JumpTopOfQueue(id) {
	new Ajax.Request('queue/switch', {
		method: 	'get',
		parameters: {uid1: id, 
					 uid2: queue.jobs[0].nzo_id} });
	StoreQueueOrder();
	new Effect.Highlight(id);
	return false;
}

// change post-processing options within queue
function ChangeProcessingOption (id,op) {
	new Ajax.Request('queue/change_opts', {
		method: 'get',
		parameters: {nzo_id: id, pp: op} ,
		});
}

// remove nzb from queue
function DropNZB (nzo_id) {
	Effect.SlideUp(nzo_id,{duration:0.1}); 
	new Ajax.Request('queue/delete', {
		method: 'get',
		parameters: {uid: nzo_id} ,
		onSuccess: function(){
			var q = $("queue");
			var nzb = $(nzo_id);
			q.removeChild(nzb);
		} });	
	StoreQueueOrder();
	return false;
}

// queue verbosity file drop
function DropNZF (nzo_id, nzf_id) {
	new Ajax.Request('queue/removeNzf', {
		method: 'get',
		parameters: {'nzo_id': nzo_id, 'nzf_id': nzf_id} });	
	return false;
}

// queue verbosity re-order arrows top/up/down/bottom
function MoveNZF (nzo_id, nzf_id, action) {
	var params = nzf_id + '=on' + '&' + 'action_key=' + action;
	new Ajax.Request('queue/'+nzo_id+'/bulk_operation', {
		method: 'get',
		parameters: params });	
	return false;
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
