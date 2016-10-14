/******

        Glitter V1
        By Safihre (2015) - safihre@sabnzbd.org

        Code extended from Shiny-template
        Code examples used from Knockstrap-template

        The setup is hierarchical, 1 main ViewModel that contains:
        - ViewModel
            - QueueListModel
                - paginationModel
                - QueueModel (item 1)
                - QueueModel (item 2)
                - ...
                - QueueModel (item n+1)
            - HistoryListModel
                - paginationModel
                - HistoryModel (item 1)
                - HistoryModel (item 2)
                - ...
                - HistoryModel (item n+1)
            - Fileslisting
                - FileslistingModel (file 1)
                - FileslistingModel (file 2)
                - ...
                - FileslistingModel (file n+1)

        ViewModel also contains all the code executed on document ready and
        functions responsible for the status information, adding NZB, etc.
        The QueueModel/HistoryModel's get added to the list-models when
        jobs are added or on switching of pages (using paginationModel).
        Once added only the properties that changed during a refresh
        get updated. In the history all the detailed information is only
        updated when created and when the user clicks on a detail.
        The Fileslisting is only populated and updated when it is opened
        for one of the QueueModel's.

******/

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