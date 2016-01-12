/* =============================================================
 * bootstrap3-typeahead.js v3.1.0
 * https://github.com/bassjobsen/Bootstrap-3-Typeahead
 * =============================================================
 * Original written by @mdo and @fat
 * =============================================================
 * Copyright 2014 Bass Jobsen @bassjobsen
 *
 * Licensed under the Apache License, Version 2.0 (the 'License');
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an 'AS IS' BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 * ============================================================ */
 !function(root,factory){"use strict";"undefined"!=typeof module&&module.exports?module.exports=factory(require("jquery")):"function"==typeof define&&define.amd?define(["jquery"],function($){return factory($)}):factory(root.jQuery)}(this,function($){"use strict";var Typeahead=function(element,options){this.$element=$(element),this.options=$.extend({},$.fn.typeahead.defaults,options),this.matcher=this.options.matcher||this.matcher,this.sorter=this.options.sorter||this.sorter,this.select=this.options.select||this.select,this.autoSelect="boolean"==typeof this.options.autoSelect?this.options.autoSelect:!0,this.highlighter=this.options.highlighter||this.highlighter,this.render=this.options.render||this.render,this.updater=this.options.updater||this.updater,this.displayText=this.options.displayText||this.displayText,this.source=this.options.source,this.delay=this.options.delay,this.$menu=$(this.options.menu),this.$appendTo=this.options.appendTo?$(this.options.appendTo):null,this.shown=!1,this.listen(),this.showHintOnFocus="boolean"==typeof this.options.showHintOnFocus?this.options.showHintOnFocus:!1,this.afterSelect=this.options.afterSelect,this.addItem=!1};Typeahead.prototype={constructor:Typeahead,select:function(){var val=this.$menu.find(".active").data("value");if(this.$element.data("active",val),this.autoSelect||val){var newVal=this.updater(val);newVal||(newVal=""),this.$element.val(this.displayText(newVal)||newVal).change(),this.afterSelect(newVal)}return this.hide()},updater:function(item){return item},setSource:function(source){this.source=source},show:function(){var scrollHeight,pos=$.extend({},this.$element.position(),{height:this.$element[0].offsetHeight});scrollHeight="function"==typeof this.options.scrollHeight?this.options.scrollHeight.call():this.options.scrollHeight;var element;return element=this.shown?this.$menu:this.$appendTo?this.$menu.appendTo(this.$appendTo):this.$menu.insertAfter(this.$element),element.css({top:pos.top+pos.height+scrollHeight,left:pos.left}).show(),this.shown=!0,this},hide:function(){return this.$menu.hide(),this.shown=!1,this},lookup:function(query){if("undefined"!=typeof query&&null!==query?this.query=query:this.query=this.$element.val()||"",this.query.length<this.options.minLength)return this.shown?this.hide():this;var worker=$.proxy(function(){$.isFunction(this.source)?this.source(this.query,$.proxy(this.process,this)):this.source&&this.process(this.source)},this);clearTimeout(this.lookupWorker),this.lookupWorker=setTimeout(worker,this.delay)},process:function(items){var that=this;return items=$.grep(items,function(item){return that.matcher(item)}),items=this.sorter(items),items.length||this.options.addItem?(items.length>0?this.$element.data("active",items[0]):this.$element.data("active",null),this.options.addItem&&items.push(this.options.addItem),"all"==this.options.items?this.render(items).show():this.render(items.slice(0,this.options.items)).show()):this.shown?this.hide():this},matcher:function(item){var it=this.displayText(item);return~it.toLowerCase().indexOf(this.query.toLowerCase())},sorter:function(items){for(var item,beginswith=[],caseSensitive=[],caseInsensitive=[];item=items.shift();){var it=this.displayText(item);it.toLowerCase().indexOf(this.query.toLowerCase())?~it.indexOf(this.query)?caseSensitive.push(item):caseInsensitive.push(item):beginswith.push(item)}return beginswith.concat(caseSensitive,caseInsensitive)},highlighter:function(item){var len,leftPart,middlePart,rightPart,strong,html=$("<div></div>"),query=this.query,i=item.toLowerCase().indexOf(query.toLowerCase());if(len=query.length,0===len)return html.text(item).html();for(;i>-1;)leftPart=item.substr(0,i),middlePart=item.substr(i,len),rightPart=item.substr(i+len),strong=$("<strong></strong>").text(middlePart),html.append(document.createTextNode(leftPart)).append(strong),item=rightPart,i=item.toLowerCase().indexOf(query.toLowerCase());return html.append(document.createTextNode(item)).html()},render:function(items){var that=this,self=this,activeFound=!1;return items=$(items).map(function(i,item){var text=self.displayText(item);return i=$(that.options.item).data("value",item),i.find("a").html(that.highlighter(text)),text==self.$element.val()&&(i.addClass("active"),self.$element.data("active",item),activeFound=!0),i[0]}),this.autoSelect&&!activeFound&&(items.first().addClass("active"),this.$element.data("active",items.first().data("value"))),this.$menu.html(items),this},displayText:function(item){return"undefined"!=typeof item&&"undefined"!=typeof item.name&&item.name||item},next:function(event){var active=this.$menu.find(".active").removeClass("active"),next=active.next();next.length||(next=$(this.$menu.find("li")[0])),next.addClass("active")},prev:function(event){var active=this.$menu.find(".active").removeClass("active"),prev=active.prev();prev.length||(prev=this.$menu.find("li").last()),prev.addClass("active")},listen:function(){this.$element.on("focus",$.proxy(this.focus,this)).on("blur",$.proxy(this.blur,this)).on("keypress",$.proxy(this.keypress,this)).on("keyup",$.proxy(this.keyup,this)),this.eventSupported("keydown")&&this.$element.on("keydown",$.proxy(this.keydown,this)),this.$menu.on("click",$.proxy(this.click,this)).on("mouseenter","li",$.proxy(this.mouseenter,this)).on("mouseleave","li",$.proxy(this.mouseleave,this))},destroy:function(){this.$element.data("typeahead",null),this.$element.data("active",null),this.$element.off("focus").off("blur").off("keypress").off("keyup"),this.eventSupported("keydown")&&this.$element.off("keydown"),this.$menu.remove()},eventSupported:function(eventName){var isSupported=eventName in this.$element;return isSupported||(this.$element.setAttribute(eventName,"return;"),isSupported="function"==typeof this.$element[eventName]),isSupported},move:function(e){if(this.shown)switch(e.keyCode){case 9:case 13:case 27:e.preventDefault();break;case 38:if(e.shiftKey)return;e.preventDefault(),this.prev();break;case 40:if(e.shiftKey)return;e.preventDefault(),this.next()}},keydown:function(e){this.suppressKeyPressRepeat=~$.inArray(e.keyCode,[40,38,9,13,27]),this.shown||40!=e.keyCode?this.move(e):this.lookup()},keypress:function(e){this.suppressKeyPressRepeat||this.move(e)},keyup:function(e){switch(e.keyCode){case 40:case 38:case 16:case 17:case 18:break;case 9:case 13:if(!this.shown)return;this.select();break;case 27:if(!this.shown)return;this.hide();break;default:this.lookup()}e.preventDefault()},focus:function(e){this.focused||(this.focused=!0,this.options.showHintOnFocus&&this.lookup(""))},blur:function(e){this.focused=!1,!this.mousedover&&this.shown&&this.hide()},click:function(e){e.preventDefault(),this.select(),this.$element.focus()},mouseenter:function(e){this.mousedover=!0,this.$menu.find(".active").removeClass("active"),$(e.currentTarget).addClass("active")},mouseleave:function(e){this.mousedover=!1,!this.focused&&this.shown&&this.hide()}};var old=$.fn.typeahead;$.fn.typeahead=function(option){var arg=arguments;return"string"==typeof option&&"getActive"==option?this.data("active"):this.each(function(){var $this=$(this),data=$this.data("typeahead"),options="object"==typeof option&&option;data||$this.data("typeahead",data=new Typeahead(this,options)),"string"==typeof option&&(arg.length>1?data[option].apply(data,Array.prototype.slice.call(arg,1)):data[option]())})},$.fn.typeahead.defaults={source:[],items:8,menu:'<ul class="typeahead dropdown-menu" role="listbox"></ul>',item:'<li><a class="dropdown-item" href="#" role="option"></a></li>',minLength:1,scrollHeight:0,autoSelect:!0,afterSelect:$.noop,addItem:!1,delay:0},$.fn.typeahead.Constructor=Typeahead,$.fn.typeahead.noConflict=function(){return $.fn.typeahead=old,this},$(document).on("focus.typeahead.data-api",'[data-provide="typeahead"]',function(e){var $this=$(this);$this.data("typeahead")||$this.typeahead($this.data())})});
 
 /*!
 * jQuery Form Plugin
 * version: 3.51.0-2014.06.20
 * Requires jQuery v1.5 or later
 * Copyright (c) 2014 M. Alsup
 * Examples and documentation at: http://malsup.com/jquery/form/
 * Project repository: https://github.com/malsup/form
 * Dual licensed under the MIT and GPL licenses.
 * https://github.com/malsup/form#copyright-and-license
 */
!function(e){"use strict";"function"==typeof define&&define.amd?define(["jquery"],e):e("undefined"!=typeof jQuery?jQuery:window.Zepto)}(function(e){"use strict";function t(t){var r=t.data;t.isDefaultPrevented()||(t.preventDefault(),e(t.target).ajaxSubmit(r))}function r(t){var r=t.target,a=e(r);if(!a.is("[type=submit],[type=image]")){var n=a.closest("[type=submit]");if(0===n.length)return;r=n[0]}var i=this;if(i.clk=r,"image"==r.type)if(void 0!==t.offsetX)i.clk_x=t.offsetX,i.clk_y=t.offsetY;else if("function"==typeof e.fn.offset){var o=a.offset();i.clk_x=t.pageX-o.left,i.clk_y=t.pageY-o.top}else i.clk_x=t.pageX-r.offsetLeft,i.clk_y=t.pageY-r.offsetTop;setTimeout(function(){i.clk=i.clk_x=i.clk_y=null},100)}function a(){if(e.fn.ajaxSubmit.debug){var t="[jquery.form] "+Array.prototype.join.call(arguments,"");window.console&&window.console.log?window.console.log(t):window.opera&&window.opera.postError&&window.opera.postError(t)}}var n={};n.fileapi=void 0!==e("<input type='file'/>").get(0).files,n.formdata=void 0!==window.FormData;var i=!!e.fn.prop;e.fn.attr2=function(){if(!i)return this.attr.apply(this,arguments);var e=this.prop.apply(this,arguments);return e&&e.jquery||"string"==typeof e?e:this.attr.apply(this,arguments)},e.fn.ajaxSubmit=function(t){function r(r){var a,n,i=e.param(r,t.traditional).split("&"),o=i.length,s=[];for(a=0;o>a;a++)i[a]=i[a].replace(/\+/g," "),n=i[a].split("="),s.push([decodeURIComponent(n[0]),decodeURIComponent(n[1])]);return s}function o(a){for(var n=new FormData,i=0;i<a.length;i++)n.append(a[i].name,a[i].value);if(t.extraData){var o=r(t.extraData);for(i=0;i<o.length;i++)o[i]&&n.append(o[i][0],o[i][1])}t.data=null;var s=e.extend(!0,{},e.ajaxSettings,t,{contentType:!1,processData:!1,cache:!1,type:u||"POST"});t.uploadProgress&&(s.xhr=function(){var r=e.ajaxSettings.xhr();return r.upload&&r.upload.addEventListener("progress",function(e){var r=0,a=e.loaded||e.position,n=e.total;e.lengthComputable&&(r=Math.ceil(a/n*100)),t.uploadProgress(e,a,n,r)},!1),r}),s.data=null;var c=s.beforeSend;return s.beforeSend=function(e,r){r.data=t.formData?t.formData:n,c&&c.call(this,e,r)},e.ajax(s)}function s(r){function n(e){var t=null;try{e.contentWindow&&(t=e.contentWindow.document)}catch(r){a("cannot get iframe.contentWindow document: "+r)}if(t)return t;try{t=e.contentDocument?e.contentDocument:e.document}catch(r){a("cannot get iframe.contentDocument: "+r),t=e.document}return t}function o(){function t(){try{var e=n(g).readyState;a("state = "+e),e&&"uninitialized"==e.toLowerCase()&&setTimeout(t,50)}catch(r){a("Server abort: ",r," (",r.name,")"),s(k),j&&clearTimeout(j),j=void 0}}var r=f.attr2("target"),i=f.attr2("action"),o="multipart/form-data",c=f.attr("enctype")||f.attr("encoding")||o;w.setAttribute("target",p),(!u||/post/i.test(u))&&w.setAttribute("method","POST"),i!=m.url&&w.setAttribute("action",m.url),m.skipEncodingOverride||u&&!/post/i.test(u)||f.attr({encoding:"multipart/form-data",enctype:"multipart/form-data"}),m.timeout&&(j=setTimeout(function(){T=!0,s(D)},m.timeout));var l=[];try{if(m.extraData)for(var d in m.extraData)m.extraData.hasOwnProperty(d)&&l.push(e.isPlainObject(m.extraData[d])&&m.extraData[d].hasOwnProperty("name")&&m.extraData[d].hasOwnProperty("value")?e('<input type="hidden" name="'+m.extraData[d].name+'">').val(m.extraData[d].value).appendTo(w)[0]:e('<input type="hidden" name="'+d+'">').val(m.extraData[d]).appendTo(w)[0]);m.iframeTarget||v.appendTo("body"),g.attachEvent?g.attachEvent("onload",s):g.addEventListener("load",s,!1),setTimeout(t,15);try{w.submit()}catch(h){var x=document.createElement("form").submit;x.apply(w)}}finally{w.setAttribute("action",i),w.setAttribute("enctype",c),r?w.setAttribute("target",r):f.removeAttr("target"),e(l).remove()}}function s(t){if(!x.aborted&&!F){if(M=n(g),M||(a("cannot access response document"),t=k),t===D&&x)return x.abort("timeout"),void S.reject(x,"timeout");if(t==k&&x)return x.abort("server abort"),void S.reject(x,"error","server abort");if(M&&M.location.href!=m.iframeSrc||T){g.detachEvent?g.detachEvent("onload",s):g.removeEventListener("load",s,!1);var r,i="success";try{if(T)throw"timeout";var o="xml"==m.dataType||M.XMLDocument||e.isXMLDoc(M);if(a("isXml="+o),!o&&window.opera&&(null===M.body||!M.body.innerHTML)&&--O)return a("requeing onLoad callback, DOM not available"),void setTimeout(s,250);var u=M.body?M.body:M.documentElement;x.responseText=u?u.innerHTML:null,x.responseXML=M.XMLDocument?M.XMLDocument:M,o&&(m.dataType="xml"),x.getResponseHeader=function(e){var t={"content-type":m.dataType};return t[e.toLowerCase()]},u&&(x.status=Number(u.getAttribute("status"))||x.status,x.statusText=u.getAttribute("statusText")||x.statusText);var c=(m.dataType||"").toLowerCase(),l=/(json|script|text)/.test(c);if(l||m.textarea){var f=M.getElementsByTagName("textarea")[0];if(f)x.responseText=f.value,x.status=Number(f.getAttribute("status"))||x.status,x.statusText=f.getAttribute("statusText")||x.statusText;else if(l){var p=M.getElementsByTagName("pre")[0],h=M.getElementsByTagName("body")[0];p?x.responseText=p.textContent?p.textContent:p.innerText:h&&(x.responseText=h.textContent?h.textContent:h.innerText)}}else"xml"==c&&!x.responseXML&&x.responseText&&(x.responseXML=X(x.responseText));try{E=_(x,c,m)}catch(y){i="parsererror",x.error=r=y||i}}catch(y){a("error caught: ",y),i="error",x.error=r=y||i}x.aborted&&(a("upload aborted"),i=null),x.status&&(i=x.status>=200&&x.status<300||304===x.status?"success":"error"),"success"===i?(m.success&&m.success.call(m.context,E,"success",x),S.resolve(x.responseText,"success",x),d&&e.event.trigger("ajaxSuccess",[x,m])):i&&(void 0===r&&(r=x.statusText),m.error&&m.error.call(m.context,x,i,r),S.reject(x,"error",r),d&&e.event.trigger("ajaxError",[x,m,r])),d&&e.event.trigger("ajaxComplete",[x,m]),d&&!--e.active&&e.event.trigger("ajaxStop"),m.complete&&m.complete.call(m.context,x,i),F=!0,m.timeout&&clearTimeout(j),setTimeout(function(){m.iframeTarget?v.attr("src",m.iframeSrc):v.remove(),x.responseXML=null},100)}}}var c,l,m,d,p,v,g,x,y,b,T,j,w=f[0],S=e.Deferred();if(S.abort=function(e){x.abort(e)},r)for(l=0;l<h.length;l++)c=e(h[l]),i?c.prop("disabled",!1):c.removeAttr("disabled");if(m=e.extend(!0,{},e.ajaxSettings,t),m.context=m.context||m,p="jqFormIO"+(new Date).getTime(),m.iframeTarget?(v=e(m.iframeTarget),b=v.attr2("name"),b?p=b:v.attr2("name",p)):(v=e('<iframe name="'+p+'" src="'+m.iframeSrc+'" />'),v.css({position:"absolute",top:"-1000px",left:"-1000px"})),g=v[0],x={aborted:0,responseText:null,responseXML:null,status:0,statusText:"n/a",getAllResponseHeaders:function(){},getResponseHeader:function(){},setRequestHeader:function(){},abort:function(t){var r="timeout"===t?"timeout":"aborted";a("aborting upload... "+r),this.aborted=1;try{g.contentWindow.document.execCommand&&g.contentWindow.document.execCommand("Stop")}catch(n){}v.attr("src",m.iframeSrc),x.error=r,m.error&&m.error.call(m.context,x,r,t),d&&e.event.trigger("ajaxError",[x,m,r]),m.complete&&m.complete.call(m.context,x,r)}},d=m.global,d&&0===e.active++&&e.event.trigger("ajaxStart"),d&&e.event.trigger("ajaxSend",[x,m]),m.beforeSend&&m.beforeSend.call(m.context,x,m)===!1)return m.global&&e.active--,S.reject(),S;if(x.aborted)return S.reject(),S;y=w.clk,y&&(b=y.name,b&&!y.disabled&&(m.extraData=m.extraData||{},m.extraData[b]=y.value,"image"==y.type&&(m.extraData[b+".x"]=w.clk_x,m.extraData[b+".y"]=w.clk_y)));var D=1,k=2,A=e("meta[name=csrf-token]").attr("content"),L=e("meta[name=csrf-param]").attr("content");L&&A&&(m.extraData=m.extraData||{},m.extraData[L]=A),m.forceSync?o():setTimeout(o,10);var E,M,F,O=50,X=e.parseXML||function(e,t){return window.ActiveXObject?(t=new ActiveXObject("Microsoft.XMLDOM"),t.async="false",t.loadXML(e)):t=(new DOMParser).parseFromString(e,"text/xml"),t&&t.documentElement&&"parsererror"!=t.documentElement.nodeName?t:null},C=e.parseJSON||function(e){return window.eval("("+e+")")},_=function(t,r,a){var n=t.getResponseHeader("content-type")||"",i="xml"===r||!r&&n.indexOf("xml")>=0,o=i?t.responseXML:t.responseText;return i&&"parsererror"===o.documentElement.nodeName&&e.error&&e.error("parsererror"),a&&a.dataFilter&&(o=a.dataFilter(o,r)),"string"==typeof o&&("json"===r||!r&&n.indexOf("json")>=0?o=C(o):("script"===r||!r&&n.indexOf("javascript")>=0)&&e.globalEval(o)),o};return S}if(!this.length)return a("ajaxSubmit: skipping submit process - no element selected"),this;var u,c,l,f=this;"function"==typeof t?t={success:t}:void 0===t&&(t={}),u=t.type||this.attr2("method"),c=t.url||this.attr2("action"),l="string"==typeof c?e.trim(c):"",l=l||window.location.href||"",l&&(l=(l.match(/^([^#]+)/)||[])[1]),t=e.extend(!0,{url:l,success:e.ajaxSettings.success,type:u||e.ajaxSettings.type,iframeSrc:/^https/i.test(window.location.href||"")?"javascript:false":"about:blank"},t);var m={};if(this.trigger("form-pre-serialize",[this,t,m]),m.veto)return a("ajaxSubmit: submit vetoed via form-pre-serialize trigger"),this;if(t.beforeSerialize&&t.beforeSerialize(this,t)===!1)return a("ajaxSubmit: submit aborted via beforeSerialize callback"),this;var d=t.traditional;void 0===d&&(d=e.ajaxSettings.traditional);var p,h=[],v=this.formToArray(t.semantic,h);if(t.data&&(t.extraData=t.data,p=e.param(t.data,d)),t.beforeSubmit&&t.beforeSubmit(v,this,t)===!1)return a("ajaxSubmit: submit aborted via beforeSubmit callback"),this;if(this.trigger("form-submit-validate",[v,this,t,m]),m.veto)return a("ajaxSubmit: submit vetoed via form-submit-validate trigger"),this;var g=e.param(v,d);p&&(g=g?g+"&"+p:p),"GET"==t.type.toUpperCase()?(t.url+=(t.url.indexOf("?")>=0?"&":"?")+g,t.data=null):t.data=g;var x=[];if(t.resetForm&&x.push(function(){f.resetForm()}),t.clearForm&&x.push(function(){f.clearForm(t.includeHidden)}),!t.dataType&&t.target){var y=t.success||function(){};x.push(function(r){var a=t.replaceTarget?"replaceWith":"html";e(t.target)[a](r).each(y,arguments)})}else t.success&&x.push(t.success);if(t.success=function(e,r,a){for(var n=t.context||this,i=0,o=x.length;o>i;i++)x[i].apply(n,[e,r,a||f,f])},t.error){var b=t.error;t.error=function(e,r,a){var n=t.context||this;b.apply(n,[e,r,a,f])}}if(t.complete){var T=t.complete;t.complete=function(e,r){var a=t.context||this;T.apply(a,[e,r,f])}}var j=e("input[type=file]:enabled",this).filter(function(){return""!==e(this).val()}),w=j.length>0,S="multipart/form-data",D=f.attr("enctype")==S||f.attr("encoding")==S,k=n.fileapi&&n.formdata;a("fileAPI :"+k);var A,L=(w||D)&&!k;t.iframe!==!1&&(t.iframe||L)?t.closeKeepAlive?e.get(t.closeKeepAlive,function(){A=s(v)}):A=s(v):A=(w||D)&&k?o(v):e.ajax(t),f.removeData("jqxhr").data("jqxhr",A);for(var E=0;E<h.length;E++)h[E]=null;return this.trigger("form-submit-notify",[this,t]),this},e.fn.ajaxForm=function(n){if(n=n||{},n.delegation=n.delegation&&e.isFunction(e.fn.on),!n.delegation&&0===this.length){var i={s:this.selector,c:this.context};return!e.isReady&&i.s?(a("DOM not ready, queuing ajaxForm"),e(function(){e(i.s,i.c).ajaxForm(n)}),this):(a("terminating; zero elements found by selector"+(e.isReady?"":" (DOM not ready)")),this)}return n.delegation?(e(document).off("submit.form-plugin",this.selector,t).off("click.form-plugin",this.selector,r).on("submit.form-plugin",this.selector,n,t).on("click.form-plugin",this.selector,n,r),this):this.ajaxFormUnbind().bind("submit.form-plugin",n,t).bind("click.form-plugin",n,r)},e.fn.ajaxFormUnbind=function(){return this.unbind("submit.form-plugin click.form-plugin")},e.fn.formToArray=function(t,r){var a=[];if(0===this.length)return a;var i,o=this[0],s=this.attr("id"),u=t?o.getElementsByTagName("*"):o.elements;if(u&&!/MSIE [678]/.test(navigator.userAgent)&&(u=e(u).get()),s&&(i=e(':input[form="'+s+'"]').get(),i.length&&(u=(u||[]).concat(i))),!u||!u.length)return a;var c,l,f,m,d,p,h;for(c=0,p=u.length;p>c;c++)if(d=u[c],f=d.name,f&&!d.disabled)if(t&&o.clk&&"image"==d.type)o.clk==d&&(a.push({name:f,value:e(d).val(),type:d.type}),a.push({name:f+".x",value:o.clk_x},{name:f+".y",value:o.clk_y}));else if(m=e.fieldValue(d,!0),m&&m.constructor==Array)for(r&&r.push(d),l=0,h=m.length;h>l;l++)a.push({name:f,value:m[l]});else if(n.fileapi&&"file"==d.type){r&&r.push(d);var v=d.files;if(v.length)for(l=0;l<v.length;l++)a.push({name:f,value:v[l],type:d.type});else a.push({name:f,value:"",type:d.type})}else null!==m&&"undefined"!=typeof m&&(r&&r.push(d),a.push({name:f,value:m,type:d.type,required:d.required}));if(!t&&o.clk){var g=e(o.clk),x=g[0];f=x.name,f&&!x.disabled&&"image"==x.type&&(a.push({name:f,value:g.val()}),a.push({name:f+".x",value:o.clk_x},{name:f+".y",value:o.clk_y}))}return a},e.fn.formSerialize=function(t){return e.param(this.formToArray(t))},e.fn.fieldSerialize=function(t){var r=[];return this.each(function(){var a=this.name;if(a){var n=e.fieldValue(this,t);if(n&&n.constructor==Array)for(var i=0,o=n.length;o>i;i++)r.push({name:a,value:n[i]});else null!==n&&"undefined"!=typeof n&&r.push({name:this.name,value:n})}}),e.param(r)},e.fn.fieldValue=function(t){for(var r=[],a=0,n=this.length;n>a;a++){var i=this[a],o=e.fieldValue(i,t);null===o||"undefined"==typeof o||o.constructor==Array&&!o.length||(o.constructor==Array?e.merge(r,o):r.push(o))}return r},e.fieldValue=function(t,r){var a=t.name,n=t.type,i=t.tagName.toLowerCase();if(void 0===r&&(r=!0),r&&(!a||t.disabled||"reset"==n||"button"==n||("checkbox"==n||"radio"==n)&&!t.checked||("submit"==n||"image"==n)&&t.form&&t.form.clk!=t||"select"==i&&-1==t.selectedIndex))return null;if("select"==i){var o=t.selectedIndex;if(0>o)return null;for(var s=[],u=t.options,c="select-one"==n,l=c?o+1:u.length,f=c?o:0;l>f;f++){var m=u[f];if(m.selected){var d=m.value;if(d||(d=m.attributes&&m.attributes.value&&!m.attributes.value.specified?m.text:m.value),c)return d;s.push(d)}}return s}return e(t).val()},e.fn.clearForm=function(t){return this.each(function(){e("input,select,textarea",this).clearFields(t)})},e.fn.clearFields=e.fn.clearInputs=function(t){var r=/^(?:color|date|datetime|email|month|number|password|range|search|tel|text|time|url|week)$/i;return this.each(function(){var a=this.type,n=this.tagName.toLowerCase();r.test(a)||"textarea"==n?this.value="":"checkbox"==a||"radio"==a?this.checked=!1:"select"==n?this.selectedIndex=-1:"file"==a?/MSIE/.test(navigator.userAgent)?e(this).replaceWith(e(this).clone(!0)):e(this).val(""):t&&(t===!0&&/hidden/.test(a)||"string"==typeof t&&e(this).is(t))&&(this.value="")})},e.fn.resetForm=function(){return this.each(function(){("function"==typeof this.reset||"object"==typeof this.reset&&!this.reset.nodeType)&&this.reset()})},e.fn.enable=function(e){return void 0===e&&(e=!0),this.each(function(){this.disabled=!e})},e.fn.selected=function(t){return void 0===t&&(t=!0),this.each(function(){var r=this.type;if("checkbox"==r||"radio"==r)this.checked=t;else if("option"==this.tagName.toLowerCase()){var a=e(this).parent("select");t&&a[0]&&"select-one"==a[0].type&&a.find("option").selected(!1),this.selected=t}})},e.fn.ajaxSubmit.debug=!1});

/*!
 * jQuery PathBrowser
 *
 * (c) 2012 SABnzbd Team, Inc. All rights reserved.
 *
 * Dual licensed under MIT or GPLv2 licenses
 *   http://en.wikipedia.org/wiki/MIT_License
 *   http://en.wikipedia.org/wiki/GNU_General_Public_License
 *
 * Changed by Safihre - 11 Nov 2015
*/
;(function($) {
    // Building object
    function FileBrowser(element) {
        // Initialize
        this.element = $(element);
        this.initialDir = null;
        this.currentBrowserPath = null;
        this.currentRequest = null;
        this.fileBrowserDialog = $('#filebrowser_modal .modal-body');
        this.fileBrowserTitle = this.element.data('title') || $('label[for="'+this.element.attr('id')+'"]').text() || '';
        
        // Start
        this.init()
    };
    
    // Adding button
    FileBrowser.prototype.init = function () {
        // Self-reference
        var self = this;
        
        // Small or big button
        buttonText = this.element.hasClass('fileBrowserSmall') ? '' : configTranslate.browseText;
        
        // Add button
        this.element.addClass('fileBrowserField').after(
            $('<button class="btn btn-default fileBrowser" type="button"><span class="glyphicon glyphicon-folder-open"></span> '+buttonText+'</button>').click(function () {
                self.openBrowser();
            })
        )   
    }
    
    // Open browser-window
    FileBrowser.prototype.openBrowser = function() {
        // Self-reference
        var self = this;
        
        // set up the browser and launch the dialog
        // textbox (not saved) path > textbox (saved) path > none
        this.initialDir = this.element.val() || this.element.data('initialdir') ||  '';
        
        // If there's no seperator, it must be a relative path
        if(this.initialDir.split(folderSeperator).length < 2 && this.element.data('initialdir')) {
            this.initialDir = this.element.data('initialdir') + folderSeperator + this.element.val();
        }

        // Browse
        this.browse(this.initialDir , folderBrowseUrl);
        
        // Choose path and close modal
        $('#filebrowser_modal_accept').click(function() {
            // Is it a relative path?
            if(self.currentBrowserPath.indexOf(self.element.data('initialdir')) === 0) {
                // Remove start
                self.currentBrowserPath = self.currentBrowserPath.replace(self.element.data('initialdir')+folderSeperator, '');
                // If it's identical to the initial dir the replacement won't work
                if(self.currentBrowserPath == self.element.data('initialdir')) {
                    self.currentBrowserPath = '';
                }
            }
            
            // Changed?
            if(self.element.val() != self.currentBrowserPath) {
                self.element.val(self.currentBrowserPath);
                formHasChanged = true;
            }
            
            // Hide and stop default action
            $('#filebrowser_modal').modal('hide');
            return false;
        })

        // Show hidden folders
        $('#show_hidden_folders').off('change')
        $('#show_hidden_folders').on('change', function() {
        	self.browse(self.currentBrowserPath , folderBrowseUrl);
        })
        
        // Use custom title instead of default and open modal
        $('#filebrowser_modal .modal-header h4').text(this.fileBrowserTitle);
        $('#filebrowser_modal').modal('show');
        return false;
    }
    
    FileBrowser.prototype.browse = function(path, endpoint) {
        // Self-reference
        var self = this;
        
        // Still loading
        if (this.currentRequest) this.currentRequest.abort();

        // Show hidden folders on Linux?
        var extraHidden = $('#show_hidden_folders').is(':checked') ? '&show_hidden_folders=1' : '';
        
        // Get current folders
        this.currentBrowserPath = path;
        this.currentRequest = $.getJSON(endpoint + extraHidden, { name: path }, function (data) {
            // Clean
            self.fileBrowserDialog.empty();
            
            // Make list
            var list = $('<div class="list-group">').appendTo(self.fileBrowserDialog);
            $.each(data.paths, function (i, entry) {
                // Title for first one
                if(i == 0) {
                    self.fileBrowserDialog.prepend($('<h4>').text(entry.current_path))
                    return
                }
                // Regular link
                link = $('<a class="list-group-item" href="javascript:void(0)" />').click(function () { 
                    self.browse(entry.path, endpoint); }
                ).text(entry.name);
                // Back image
                if(entry.name == '..') {
                    $('<span class="glyphicon glyphicon-arrow-left"></span> ').prependTo(link);
                } else {
                    $('<span class="glyphicon glyphicon-folder-open"></span> ').prependTo(link);
                }
                // Add to list
                link.appendTo(list);
            });
            
        });
    }
    
    // Make sure we have unique instances
    $.fn.fileBrowser = function () {
        return this.each(function () {
            if (!$.data(this, 'plugin_FileBrowser')) {
                $.data(this, 'plugin_FileBrowser', new FileBrowser(this));
            }
        });
    }
})(jQuery);

/*!
 * Config JS
 *
 * (c) 2015 SABnzbd Team, Inc. All rights reserved.
 */
function config_success() {
    $('.saveButton').each(function () {
        $(this).removeAttr("disabled").html('<span class="glyphicon glyphicon-ok"></span> '+configTranslate.saveChanges);
    });
    // Let us leave!
    formWasSubmitted = true;
    formHasChanged = false;
}
function config_failure() {
    $('.saveButton').each(function () {
        $(this).removeAttr("disabled").html('<span class="glyphicon glyphicon-remove"></span> '+configTranslate.failed);
    });
    // Can't go yet..
    formWasSubmitted = false;
}
function do_restart() {
    // Show overlay
    $('.main-restarting').show()
    
    // What template
    var arrPath = window.location.pathname.split('/');
    var urlPath = (arrPath[1] == "m" || arrPath[2] == "m") ? '/sabnzbd/m/' : '/sabnzbd/';

    // Are we on settings page?
    if(!$('body').hasClass('General')) {
        // Same as before, with fall-back in case location.origin is not supported (<IE9)
        var urlTotal = window.location.origin ? (window.location.origin + urlPath) : window.location;
    } else {
        // Protocol and port depend on http(s) setting
        if($('#enable_https').is(':checked') && window.location.protocol == 'https:') {
            // Https on and we visited this page from HTTPS
            var urlProtocol = 'https:'
            var urlPort = $('#https_port').val();
        } else {
            // Regular
            var urlProtocol = 'http:';
            var urlPort = $('#port').val();
        }
        
        // We cannot make a good guess for the IP, so at least we assume that stays the same
        var urlTotal = urlProtocol + '//' + window.location.hostname + ':' + urlPort + urlPath;
    }
    
    // Show where we are going to connect
    $('.main-restarting .restarting-url').text(urlTotal)
    
    // Initiate restart
    $.ajax({ url: '../../config/restart?session=' + sabSession, 
        complete: function() {
            // Keep counter of failures
            var failureCounter = 0;
    
            // Now we try untill we can connect
            var refreshInterval = setInterval(function() {
                $.ajax({ url: urlTotal, 
                    success: function() {
                        // Back to base
                        location.href = urlTotal;
                    },
                    error: function(status, text) {
                        failureCounter = failureCounter+1;
                        // Too many failuers and we give up
                        if(failureCounter >= 7) {
                            // If the port has changed 'Access-Control-Allow-Origin' header will not allow
                            // us to check if the server is back up. So after 7 failures we redirect
                            // anyway in the hopes it works anyway..
                            location.href = urlTotal;
                        }
                    }
                })
            }, 5000)
            
            // Exception if we go from HTTPS to HTTP 
            // (this is not allowed by browsers and all of the above will be ignored)
            if(window.location.protocol != urlProtocol) {
                // Saftey redirect after 40 sec
                setTimeout(function() {
                    location.href = urlTotal;
                }, 40*1000)
            }
        }
    });
}

$(document).ready(function () {
    /**
        Restart function
    **/
    $('.sabnzbd_restart').click(function () {
        $('.sabnzbd_restart').each(function () {
            $(this).attr("disabled", "disabled");
        });
        if (confirm(configTranslate.explainRestart.replace(/\<br(\s*\/|)\>/g, '\n'))) {
            $(this).attr("value", configTranslate.wizzardRestart);
            // Let us leave!
            formWasSubmitted = true;
            do_restart();
        }
        $('.sabnzbd_restart').each(function () {
            $(this).removeAttr("disabled");
        });
        return false;
    });

    /**
        Submit the form
    **/
    $('.fullform').ajaxForm({
        datatype: 'json',
        beforeSubmit: function () {
            $('.saveButton').each(function () {
                $(this).attr("disabled", "disabled").html('<span class="glyphicon glyphicon-transfer"></span> ' + configTranslate.saving);
            });
        },
        success: function (json) {
            if (json.error) {
               $('#config_err_msg').text(json.error);
               setTimeout(config_failure, 1000);
            } else if(json.value && json.value.restart_req) {
                // Trigger restart question
                if(confirm(configTranslate.needRestart + "\n" + configTranslate.buttonRestart + " SABnzbd?")) {
                    // No more questions
                    do_restart();
                } else {
                    $('#config_err_msg').text(" ");
                    setTimeout(config_success, 1000);
                }
            } else {
               $('#config_err_msg').text(" ");
               setTimeout(config_success, 1000);
            }
        },
        error: function () {
            setTimeout(config_failure, 1000);
        },
        timeout: 3000
    });

    /**
        Form changes tracking
    **/
    $(document).on("submit", "form", function(event){
        // Let us leave!
        formWasSubmitted = true;
        formHasChanged = false;
    });
    $(document).on('change', 'form input[type!="submit"][type!="button"], form select, form textarea', function (e) {
        formHasChanged = true;
        formWasSubmitted = false;
    });
    window.onbeforeunload = function (e) {
        if (formHasChanged && !formWasSubmitted) {
            var message = configTranslate.confirmLeave, e = e || window.event;
            if (e) {
                e.returnValue = message;
            }
            return message;
        }
    }
    
    // Fix for touch devices needing double click on the menu
    $('.navbar-nav li a').on('touchstart', function(e) {
        $(this).click()
    })
    
    // Add hover to checkboxes (can't do it with CSS)
    $('input[type="checkbox"]').siblings('label').addClass('config-hover')
    $('input[type="checkbox"]').parents('label').addClass('config-hover')
});

/*
 * Takes the inputs-elements found in the current selector
 * and extracts the values into the provided data-object.
 */
$.fn.extractFormDataTo = function(target) {
    var inputs = $("input[type != 'submit'][type != 'button']", this);

    // could use .serializeArray() but that omits unchecked items
    inputs.each(function (i,elem) {
        target[elem.name] = elem.value;
    });

    return this;
}