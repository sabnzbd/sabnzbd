function toggleWebPass()
{
  var web
  web = $('#enable_webpass').attr('checked')
  if ($('#enable_webpass').attr('checked') == 1)
  {
    $('#web_user').attr("disabled","");
    $('#web_pass').attr("disabled","");

  } else {
    $('#web_user').attr("disabled","disabled");
    $('#web_pass').attr("value","");
    $('#web_pass').attr("disabled","disabled");
    $('#web_user').attr("value","");
  }
};


function checkRequired()
{
  if ($("#bandwidth").val())
  {
    $("#next-button").removeAttr("disabled");
  } else {
    $("#next-button").attr("disabled","disabled");
  }
};


$(document).ready(function() {
  checkRequired();
  toggleWebPass();

  $(".validate-text-required").blur(function(){
    if (this.value || this.checked){
      $(this).removeClass("incorrect");
      $(this).addClass("correct");
    } else {
      $(this).removeClass("correct");
      $(this).addClass("incorrect");
    }
  });
  $("#bandwidth").bind('keyup blur',function(){
    if (this.value){
      $(this).removeClass("incorrect");
      $(this).addClass("correct");
      $("#bandwidth-tip").removeClass("hidden");
      $("#bandwidth-error").addClass("hidden");
      checkRequired();
    } else {
      $(this).removeClass("correct");
      $(this).addClass("incorrect");
      $("#bandwidth-tip").addClass("hidden");
      $("#bandwidth-error").removeClass("hidden");
      checkRequired();
    }
  });

  $('#enable_webpass').bind('change click focus', function() {
  toggleWebPass();
  });
});