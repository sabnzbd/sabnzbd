// refresh time in seconds
RefreshTime = 5;


PARSE_RE = /SABNZBDJSON\s+((?:.|\s)*)\s+-->/;
prev_nzb = null;



function getInfo(callbackFn)
{
	var req;
	
	// if not IE (browsers that use XMLHttpRequest)
	if (window.XMLHttpRequest){
		req = new XMLHttpRequest();
	}
	// if IE (browsers that use ActiveXObject)
	else if (window.ActiveXObject) {
		req = new ActiveXObject("Microsoft.XMLHTTP");
	}
	
	
	
	function parseReq(evt)
	{
		// we don't give a shit if it hasnt loaded yet
		if (req.readyState != 4)
			return;
		
		// oh fuck an error
		if (req.status != 200)
		{
			callbackFn("error");
			return;
		}
		
		
		var m = PARSE_RE.exec(req.responseText);
		
		var ret;
		if (m != null) {
			//t.innerHTML += xml;
			ret = eval('('+m[1]+');');
			
			//for (a in r) {
			//	t.innerHTML += a + ": " + r[a] + "<br>\n";
			//}
		}
		else {
			ret = "error";
		}
		
		callbackFn(ret);
	}
	req.onreadystatechange = parseReq;
	req.open('POST', '/sabnzbd/queue/', true);
	// IE6 sucks it with caching, and sabnzbd screws up with get parameters
	req.send('stump='+Math.random());
}

function parseInfo(info)
{	
	if (info == "error") {
		
	}
	else {

		var jobs = info["jobs"];
		for (var x in jobs) {
			var job = jobs[x];
			var id = job["id"];
			
			// something was added
			if (document.getElementById("name_"+id) == null) { 
				window.location = window.location;
				return;
			}
			else {


				var goodname = job["name"];
				var pidstrip = "N/A";
				if (job["msgid"] != "") {
				  pidstrip = job["msgid"]
				}
				
//				if (document.getElementById("name_"+id).innerHTML != goodname)
					 document.getElementById("name_"+id).innerHTML = goodname;
				document.getElementById("left_"+id).innerHTML = job["left"].toFixed(2);
				document.getElementById("total_"+id).innerHTML = job["total"].toFixed(2);
				document.getElementById("eta_"+id).innerHTML = job["eta"];
				document.getElementById("age_"+id).innerHTML = job["age"];
				var pct = (job["total"] > 0) ? (job["total"]-job["left"])/(job["total"])*100.0 : 0;
				document.getElementById("progress_"+id).style.width = pct+"%";
				
				// determine "Time Left"
				var timeleft = "<img src=\"../static/images/icon_infinity.png\" alt=\"Many hours later...\" />";
				if (info["speed"] >= 1 && job["total"] > 0) {
					var kbleft = job["left"] * 1024;
					var hoursleft = 0;
					var minsleft = 0;
					var secsleft = Math.round(kbleft / info["speed"]);
					if (secsleft>=60) {
						minsleft = Math.round(secsleft/60);
						secsleft = secsleft%60;
					}
					if (minsleft>=60) {
						hoursleft = Math.round(minsleft/60);
						minsleft = minsleft%60;
					}
					timeleft  = "<b>" + 	((hoursleft < 10) ?  "0" : "") + hoursleft;
					timeleft += 			((minsleft  < 10) ? ":0" : ":") + minsleft;
					timeleft += 			((secsleft  < 10) ? ":0" : ":") + secsleft + "</b>";
				}
				document.getElementById("timeleft_"+id).innerHTML = timeleft;
									
				// hop	
				if (pidstrip == "N/A")
					document.getElementById("hop_"+id).innerHTML = "N/A";
				else
					document.getElementById("hop_"+id).innerHTML = "<a href=\"https://v3.newzbin.com/browse/post/" + job["msgid"] + "\" title=\"View Newzbin Post #" + pidstrip + "\" target=\"_blank\"><img src=\"../static/images/icon_newzbin.png\" alt=\"Newzbin\" /></a>";
				
				
	
			}
		}
		
		if (prev_nzb != null)
		{
			// something finished/was deleted
			if (jobs.length != prev_nzb.length) {
				window.location = window.location;
				return;
			}
			
			// or something was moved
			for (var i in prev_nzb) {
				if (jobs[i]["id"] != prev_nzb[i]["id"]) {
					window.location = window.location;
					return;
				}
			}
		}
		prev_nzb = jobs;
	}
	
	setTimeout("doit();", RefreshTime*1000);
}

function doit()
{
	getInfo(parseInfo);
}