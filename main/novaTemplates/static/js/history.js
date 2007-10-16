// refresh time in seconds
RefreshTime = 10;


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
	req.open('POST', '/sabnzbd/history/', true);
	// IE6 sucks it with caching, and sabnzbd screws up with get parameters
	req.send('stump='+Math.random());
}

var last_loaded = "";
function parseInfo(info)
{	
	if (info == "error") {

	}
	else {

		var jobs = info["jobs"];
		for (var x in jobs) {
			var job = jobs[x];
			var filename = job["filename"];
			
			if (document.getElementById("name_"+filename) == null) { 
				// something was added, refresh frame
				setTimeout("window.location = window.location;",RefreshTime*1000);
				// ^^^ temporary refresh bug fix 8 - )
				return;
			}
			else {
				if (job["loaded"] == 'True') {
					// processing
					document.getElementById("loaded_"+filename).innerHTML = '<img src="../static/images/dynamite.png" title="SABnzbd is currently processing these files... please hold" />&nbsp;';
					last_loaded = filename;
	
				} else if (last_loaded != "" && last_loaded == filename) {
					// it was loaded, now it's not, reload the page for proper CSS backgrounds + table structure (sometimes verbosity shows multiple rows)
					window.location = window.location;
					return;
				}
			}
		}
	}
	
	setTimeout("doit();", RefreshTime*1000);
}

function doit()
{
	getInfo(parseInfo);
}