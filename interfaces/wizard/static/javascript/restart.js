function complete() {
    $(".hidden").fadeIn("slow");
    $(".disabled").addClass('btn-success').removeClass('btn-default').removeClass('disabled');
    $('#restarting').addClass("hidden");
    $('#complete').removeClass("hidden");
    $('#tips').removeClass("hidden");
}
$(document).ready(function() {
    $.ajax({
        type: "POST",
        url: "../tapi",
        data: "mode=restart&apikey=" + $('#apikey').val(),
        complete: function(result) {
            setTimeout(complete, 7000);
        }
    });
});