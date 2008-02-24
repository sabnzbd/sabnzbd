
/* Greybox Redux
 * Written by: John Resig
 * License: LGPL (see LGPL.txt)
 */
var GB_DONE = false;
function GB_show(caption, url, height, width) {

	// Config's floating window default dimensions:
    GB_WIDTH  = 810;
    GB_HEIGHT = 535;

  if(!GB_DONE) {
    $(document.body)
      .append("<div id='GB_overlay'></div><div id='GB_window'><div id='GB_caption'></div>"
        + "<img src='static/images/icon_config_close.png' style='padding-right: 5px;' alt='Close window'/></div>");
    $("#GB_window img").click(GB_hide);
    $("#GB_overlay").click(GB_hide);
    $(window).resize(GB_position);
    GB_DONE = true;
  }
  $("#GB_frame").remove();
  $("#GB_window").append("<iframe id='GB_frame' src='"+url+"'></iframe>");
  $("#GB_caption").html(caption);
  $("#GB_overlay").show();
  GB_position();
  //if(GB_ANIMATION)
  //  $("#GB_window").slideDown("slow");
  //else
  $("#GB_window").show();

	$("#GB_window").corner({
		tl: { radius: 15 },
		tr: { radius: 15 },
		bl: { radius: 15 },
		br: { radius: 15 },
		antiAlias: true,
		autoPad: false,
		validTags: ["div"]
	});

}

function GB_hide() {
  $("#GB_window,#GB_overlay").hide();
}

function GB_position() {
  var de = document.documentElement;
  var w = self.innerWidth || (de&&de.clientWidth) || document.body.clientWidth;
//  $("#GB_window").css({width:GB_WIDTH+"px",height:GB_HEIGHT+"px", left: ((w - GB_WIDTH)/2)+"px" });
//  $("#GB_frame").css("height",GB_HEIGHT - 42 +"px");
  $("#GB_window").css({width:GB_WIDTH+"px",height:"515px", left: ((w - GB_WIDTH)/2)+"px" });
  $("#GB_frame").css("height",GB_HEIGHT - 42 +"px");
}
