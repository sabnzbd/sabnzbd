var store;
var storeFiles;
var autoreload = 10;
var currentFile;
var queueGrid;
var filesGrid;
var paused = false;
var statusTemplate;
var state2;
var southHeight;
var storeHistory;
var selectedNo; //used for keeping track of how many items were selected when an action was done
var pauseIgnore = false; //prevent the toggling of the pause button on page load from entering a pause/unpause loop
