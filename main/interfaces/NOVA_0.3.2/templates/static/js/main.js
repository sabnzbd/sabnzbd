// refresh time in seconds
RefreshTime = 5;


PARSE_RE = /SABNZBDJSON\s+((?:.|\s)*)\s+-->/;
prev_nzb = null;


function getInfo(callbackFn)
{
	var req;
	
	if (window.XMLHttpRequest){
		req = new XMLHttpRequest();
	}
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
	req.open('POST', '/sabnzbd/', true);
	// IE6 sucks it with caching, and sabnzbd fucks up with get parameters
	req.send('stump='+Math.random());
}

function parseInfo(info)
{	
	if (info == "error") {
		
	}
	else {
		document.getElementById("freedown").innerHTML = info["freedown"].toFixed(2);
		if (info["freedown"].toFixed(2) != info["freecomp"].toFixed(2))
			document.getElementById("freecomp").innerHTML = info["freecomp"].toFixed(2);
		document.getElementById("speed").innerHTML = info["speed"].toFixed(2);
		document.getElementById("left").innerHTML = info["left"].toFixed(2);
		document.getElementById("total").innerHTML = info["total"].toFixed(2);
		if (info["nzb_quota"])
			document.getElementById("nzb_quota").innerHTML = info["nzb_quota"];
		if (info["paused"] == 'True')
			document.getElementById("paused").innerHTML = '<div class="paused">PAUSED</div>';
		else
			document.getElementById("paused").innerHTML = "";
		if (info["shutdown"] == 'True')
			document.getElementById("shutdown").innerHTML = '<div class="paused">SHUTDOWN</div>';
		else
			document.getElementById("shutdown").innerHTML = "";
		
		// determine "Time Left"
		var timeleft = '<img src="static/images/icon_infinity.png" alt="Many hours later..." />';
		if (info["speed"] >= 1 && info["total"] > 0) {
			var kbleft = info["left"] * 1024;
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
		document.getElementById("totaltimeleft").innerHTML = timeleft;
		var pct = (info["total"] > 0) ? ((info["total"]-info["left"])/(info["total"])*100.0).toFixed(0) : 0;
		document.getElementById("downloaded").style.width = pct+"%";
		document.getElementById("percentdone").innerHTML = pct;
		
		
	}
	
	setTimeout("doit();", RefreshTime*1000);
}
function doit()
{
	// This initiates the ajax
	getInfo(parseInfo);
	
	// This is for show hide of toolbox content
	var button1 = $('toolboxToggle');
	var content1 = $('toolbox');
	var b1Toggle = new Fx.Style('toolbox', 'height',{duration: 250});
	button1.addEvent('click', function(){
	  if(content1.getStyle('height').toInt() > 0){
	  b1Toggle.start(0);
	  }else{
		b1Toggle.start(c1Height);
	  }
	  button1.toggleClass('toolboxToggle_');
	  return false;
	});
	content1.setStyle('display','block');
	var c1Height = content1.getSize().scrollSize.y;
	
}

