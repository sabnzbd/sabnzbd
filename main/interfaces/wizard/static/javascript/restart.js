function complete(){
    $(".hidden").fadeIn("slow");
    $(".disabled").removeAttr('disabled');
    $('#restarting').addClass("hidden");
    $('#complete').removeClass("hidden");
    $('#tips').removeClass("hidden");
}
$(document).ready(function() {
    $.ajax({
        type: "POST",
        url: "../tapi",
        data: "mode=restart",
        complete: function(result){
            setTimeout(complete,7000);
        }
    });
});