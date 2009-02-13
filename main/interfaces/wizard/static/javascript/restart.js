function complete(){
    result = "Setup is now complete!"
    cls = "success"
    r = '<span class="' + cls + '">' + result + '</span>';
    $('#restart').html(r);
    $(".hidden").fadeIn("slow");
}
$(document).ready(function() {
    $.ajax({
        type: "POST",
        url: "../tapi",
        data: "mode=restart",
        complete: function(result){
            setTimeout(complete,5000);
        }
    });
});