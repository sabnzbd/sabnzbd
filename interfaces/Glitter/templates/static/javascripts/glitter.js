/******
        
        Glitter V1
        By Safihre (2015) - safihre@sabnzbd.org
        
        Code extended from Shiny-template
        Code examples used from Knockstrap-template

********/

#include raw $webdir + "/static/javascripts/glitter.basic.js"#

/**
    GLITTER CODE
**/
\$(function() {
    'use strict';

    #include raw $webdir + "/static/javascripts/glitter.main.js"#
    #include raw $webdir + "/static/javascripts/glitter.queue.js"#
    #include raw $webdir + "/static/javascripts/glitter.history.js"#
    #include raw $webdir + "/static/javascripts/glitter.filelist.pagination.js"#

    // GO!!!
    ko.applyBindings(new ViewModel(), document.getElementById("sabnzbd"));
});