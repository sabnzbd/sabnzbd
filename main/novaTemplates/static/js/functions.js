window.onload = function(){

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

};
