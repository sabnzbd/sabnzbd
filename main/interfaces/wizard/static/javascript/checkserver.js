$(document).ready(function() {
    $("#serverTest").click(function(){
        $('#serverResponse').html('Checking...');
        $.ajax({
            type: "POST",
            url: "servertest",
            data: $("form").serialize(),
            success: function(result){
                if (result == "Connected Successfully!"){
                    cls = "success"
                } else {
                    cls = "failed"
                }
                r = '<span class="' + cls + '">' + result + '</span>';
                $('#serverResponse').html(r);
            }
        });
    });
});