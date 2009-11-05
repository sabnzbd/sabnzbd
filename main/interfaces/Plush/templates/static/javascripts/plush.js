/*
 * jQuery JavaScript Library v1.3.2
 * http://jquery.com/
 *
 * Copyright (c) 2009 John Resig
 * Dual licensed under the MIT and GPL licenses.
 * http://docs.jquery.com/License
 *
 * Date: 2009-02-19 17:34:21 -0500 (Thu, 19 Feb 2009)
 * Revision: 6246
 */
(function(){var l=this,g,y=l.jQuery,p=l.$,o=l.jQuery=l.$=function(E,F){return new o.fn.init(E,F)},D=/^[^<]*(<(.|\s)+>)[^>]*$|^#([\w-]+)$/,f=/^.[^:#\[\.,]*$/;o.fn=o.prototype={init:function(E,H){E=E||document;if(E.nodeType){this[0]=E;this.length=1;this.context=E;return this}if(typeof E==="string"){var G=D.exec(E);if(G&&(G[1]||!H)){if(G[1]){E=o.clean([G[1]],H)}else{var I=document.getElementById(G[3]);if(I&&I.id!=G[3]){return o().find(E)}var F=o(I||[]);F.context=document;F.selector=E;return F}}else{return o(H).find(E)}}else{if(o.isFunction(E)){return o(document).ready(E)}}if(E.selector&&E.context){this.selector=E.selector;this.context=E.context}return this.setArray(o.isArray(E)?E:o.makeArray(E))},selector:"",jquery:"1.3.2",size:function(){return this.length},get:function(E){return E===g?Array.prototype.slice.call(this):this[E]},pushStack:function(F,H,E){var G=o(F);G.prevObject=this;G.context=this.context;if(H==="find"){G.selector=this.selector+(this.selector?" ":"")+E}else{if(H){G.selector=this.selector+"."+H+"("+E+")"}}return G},setArray:function(E){this.length=0;Array.prototype.push.apply(this,E);return this},each:function(F,E){return o.each(this,F,E)},index:function(E){return o.inArray(E&&E.jquery?E[0]:E,this)},attr:function(F,H,G){var E=F;if(typeof F==="string"){if(H===g){return this[0]&&o[G||"attr"](this[0],F)}else{E={};E[F]=H}}return this.each(function(I){for(F in E){o.attr(G?this.style:this,F,o.prop(this,E[F],G,I,F))}})},css:function(E,F){if((E=="width"||E=="height")&&parseFloat(F)<0){F=g}return this.attr(E,F,"curCSS")},text:function(F){if(typeof F!=="object"&&F!=null){return this.empty().append((this[0]&&this[0].ownerDocument||document).createTextNode(F))}var E="";o.each(F||this,function(){o.each(this.childNodes,function(){if(this.nodeType!=8){E+=this.nodeType!=1?this.nodeValue:o.fn.text([this])}})});return E},wrapAll:function(E){if(this[0]){var F=o(E,this[0].ownerDocument).clone();if(this[0].parentNode){F.insertBefore(this[0])}F.map(function(){var G=this;while(G.firstChild){G=G.firstChild}return G}).append(this)}return this},wrapInner:function(E){return this.each(function(){o(this).contents().wrapAll(E)})},wrap:function(E){return this.each(function(){o(this).wrapAll(E)})},append:function(){return this.domManip(arguments,true,function(E){if(this.nodeType==1){this.appendChild(E)}})},prepend:function(){return this.domManip(arguments,true,function(E){if(this.nodeType==1){this.insertBefore(E,this.firstChild)}})},before:function(){return this.domManip(arguments,false,function(E){this.parentNode.insertBefore(E,this)})},after:function(){return this.domManip(arguments,false,function(E){this.parentNode.insertBefore(E,this.nextSibling)})},end:function(){return this.prevObject||o([])},push:[].push,sort:[].sort,splice:[].splice,find:function(E){if(this.length===1){var F=this.pushStack([],"find",E);F.length=0;o.find(E,this[0],F);return F}else{return this.pushStack(o.unique(o.map(this,function(G){return o.find(E,G)})),"find",E)}},clone:function(G){var E=this.map(function(){if(!o.support.noCloneEvent&&!o.isXMLDoc(this)){var I=this.outerHTML;if(!I){var J=this.ownerDocument.createElement("div");J.appendChild(this.cloneNode(true));I=J.innerHTML}return o.clean([I.replace(/ jQuery\d+="(?:\d+|null)"/g,"").replace(/^\s*/,"")])[0]}else{return this.cloneNode(true)}});if(G===true){var H=this.find("*").andSelf(),F=0;E.find("*").andSelf().each(function(){if(this.nodeName!==H[F].nodeName){return}var I=o.data(H[F],"events");for(var K in I){for(var J in I[K]){o.event.add(this,K,I[K][J],I[K][J].data)}}F++})}return E},filter:function(E){return this.pushStack(o.isFunction(E)&&o.grep(this,function(G,F){return E.call(G,F)})||o.multiFilter(E,o.grep(this,function(F){return F.nodeType===1})),"filter",E)},closest:function(E){var G=o.expr.match.POS.test(E)?o(E):null,F=0;return this.map(function(){var H=this;while(H&&H.ownerDocument){if(G?G.index(H)>-1:o(H).is(E)){o.data(H,"closest",F);return H}H=H.parentNode;F++}})},not:function(E){if(typeof E==="string"){if(f.test(E)){return this.pushStack(o.multiFilter(E,this,true),"not",E)}else{E=o.multiFilter(E,this)}}var F=E.length&&E[E.length-1]!==g&&!E.nodeType;return this.filter(function(){return F?o.inArray(this,E)<0:this!=E})},add:function(E){return this.pushStack(o.unique(o.merge(this.get(),typeof E==="string"?o(E):o.makeArray(E))))},is:function(E){return !!E&&o.multiFilter(E,this).length>0},hasClass:function(E){return !!E&&this.is("."+E)},val:function(K){if(K===g){var E=this[0];if(E){if(o.nodeName(E,"option")){return(E.attributes.value||{}).specified?E.value:E.text}if(o.nodeName(E,"select")){var I=E.selectedIndex,L=[],M=E.options,H=E.type=="select-one";if(I<0){return null}for(var F=H?I:0,J=H?I+1:M.length;F<J;F++){var G=M[F];if(G.selected){K=o(G).val();if(H){return K}L.push(K)}}return L}return(E.value||"").replace(/\r/g,"")}return g}if(typeof K==="number"){K+=""}return this.each(function(){if(this.nodeType!=1){return}if(o.isArray(K)&&/radio|checkbox/.test(this.type)){this.checked=(o.inArray(this.value,K)>=0||o.inArray(this.name,K)>=0)}else{if(o.nodeName(this,"select")){var N=o.makeArray(K);o("option",this).each(function(){this.selected=(o.inArray(this.value,N)>=0||o.inArray(this.text,N)>=0)});if(!N.length){this.selectedIndex=-1}}else{this.value=K}}})},html:function(E){return E===g?(this[0]?this[0].innerHTML.replace(/ jQuery\d+="(?:\d+|null)"/g,""):null):this.empty().append(E)},replaceWith:function(E){return this.after(E).remove()},eq:function(E){return this.slice(E,+E+1)},slice:function(){return this.pushStack(Array.prototype.slice.apply(this,arguments),"slice",Array.prototype.slice.call(arguments).join(","))},map:function(E){return this.pushStack(o.map(this,function(G,F){return E.call(G,F,G)}))},andSelf:function(){return this.add(this.prevObject)},domManip:function(J,M,L){if(this[0]){var I=(this[0].ownerDocument||this[0]).createDocumentFragment(),F=o.clean(J,(this[0].ownerDocument||this[0]),I),H=I.firstChild;if(H){for(var G=0,E=this.length;G<E;G++){L.call(K(this[G],H),this.length>1||G>0?I.cloneNode(true):I)}}if(F){o.each(F,z)}}return this;function K(N,O){return M&&o.nodeName(N,"table")&&o.nodeName(O,"tr")?(N.getElementsByTagName("tbody")[0]||N.appendChild(N.ownerDocument.createElement("tbody"))):N}}};o.fn.init.prototype=o.fn;function z(E,F){if(F.src){o.ajax({url:F.src,async:false,dataType:"script"})}else{o.globalEval(F.text||F.textContent||F.innerHTML||"")}if(F.parentNode){F.parentNode.removeChild(F)}}function e(){return +new Date}o.extend=o.fn.extend=function(){var J=arguments[0]||{},H=1,I=arguments.length,E=false,G;if(typeof J==="boolean"){E=J;J=arguments[1]||{};H=2}if(typeof J!=="object"&&!o.isFunction(J)){J={}}if(I==H){J=this;--H}for(;H<I;H++){if((G=arguments[H])!=null){for(var F in G){var K=J[F],L=G[F];if(J===L){continue}if(E&&L&&typeof L==="object"&&!L.nodeType){J[F]=o.extend(E,K||(L.length!=null?[]:{}),L)}else{if(L!==g){J[F]=L}}}}}return J};var b=/z-?index|font-?weight|opacity|zoom|line-?height/i,q=document.defaultView||{},s=Object.prototype.toString;o.extend({noConflict:function(E){l.$=p;if(E){l.jQuery=y}return o},isFunction:function(E){return s.call(E)==="[object Function]"},isArray:function(E){return s.call(E)==="[object Array]"},isXMLDoc:function(E){return E.nodeType===9&&E.documentElement.nodeName!=="HTML"||!!E.ownerDocument&&o.isXMLDoc(E.ownerDocument)},globalEval:function(G){if(G&&/\S/.test(G)){var F=document.getElementsByTagName("head")[0]||document.documentElement,E=document.createElement("script");E.type="text/javascript";if(o.support.scriptEval){E.appendChild(document.createTextNode(G))}else{E.text=G}F.insertBefore(E,F.firstChild);F.removeChild(E)}},nodeName:function(F,E){return F.nodeName&&F.nodeName.toUpperCase()==E.toUpperCase()},each:function(G,K,F){var E,H=0,I=G.length;if(F){if(I===g){for(E in G){if(K.apply(G[E],F)===false){break}}}else{for(;H<I;){if(K.apply(G[H++],F)===false){break}}}}else{if(I===g){for(E in G){if(K.call(G[E],E,G[E])===false){break}}}else{for(var J=G[0];H<I&&K.call(J,H,J)!==false;J=G[++H]){}}}return G},prop:function(H,I,G,F,E){if(o.isFunction(I)){I=I.call(H,F)}return typeof I==="number"&&G=="curCSS"&&!b.test(E)?I+"px":I},className:{add:function(E,F){o.each((F||"").split(/\s+/),function(G,H){if(E.nodeType==1&&!o.className.has(E.className,H)){E.className+=(E.className?" ":"")+H}})},remove:function(E,F){if(E.nodeType==1){E.className=F!==g?o.grep(E.className.split(/\s+/),function(G){return !o.className.has(F,G)}).join(" "):""}},has:function(F,E){return F&&o.inArray(E,(F.className||F).toString().split(/\s+/))>-1}},swap:function(H,G,I){var E={};for(var F in G){E[F]=H.style[F];H.style[F]=G[F]}I.call(H);for(var F in G){H.style[F]=E[F]}},css:function(H,F,J,E){if(F=="width"||F=="height"){var L,G={position:"absolute",visibility:"hidden",display:"block"},K=F=="width"?["Left","Right"]:["Top","Bottom"];function I(){L=F=="width"?H.offsetWidth:H.offsetHeight;if(E==="border"){return}o.each(K,function(){if(!E){L-=parseFloat(o.curCSS(H,"padding"+this,true))||0}if(E==="margin"){L+=parseFloat(o.curCSS(H,"margin"+this,true))||0}else{L-=parseFloat(o.curCSS(H,"border"+this+"Width",true))||0}})}if(H.offsetWidth!==0){I()}else{o.swap(H,G,I)}return Math.max(0,Math.round(L))}return o.curCSS(H,F,J)},curCSS:function(I,F,G){var L,E=I.style;if(F=="opacity"&&!o.support.opacity){L=o.attr(E,"opacity");return L==""?"1":L}if(F.match(/float/i)){F=w}if(!G&&E&&E[F]){L=E[F]}else{if(q.getComputedStyle){if(F.match(/float/i)){F="float"}F=F.replace(/([A-Z])/g,"-$1").toLowerCase();var M=q.getComputedStyle(I,null);if(M){L=M.getPropertyValue(F)}if(F=="opacity"&&L==""){L="1"}}else{if(I.currentStyle){var J=F.replace(/\-(\w)/g,function(N,O){return O.toUpperCase()});L=I.currentStyle[F]||I.currentStyle[J];if(!/^\d+(px)?$/i.test(L)&&/^\d/.test(L)){var H=E.left,K=I.runtimeStyle.left;I.runtimeStyle.left=I.currentStyle.left;E.left=L||0;L=E.pixelLeft+"px";E.left=H;I.runtimeStyle.left=K}}}}return L},clean:function(F,K,I){K=K||document;if(typeof K.createElement==="undefined"){K=K.ownerDocument||K[0]&&K[0].ownerDocument||document}if(!I&&F.length===1&&typeof F[0]==="string"){var H=/^<(\w+)\s*\/?>$/.exec(F[0]);if(H){return[K.createElement(H[1])]}}var G=[],E=[],L=K.createElement("div");o.each(F,function(P,S){if(typeof S==="number"){S+=""}if(!S){return}if(typeof S==="string"){S=S.replace(/(<(\w+)[^>]*?)\/>/g,function(U,V,T){return T.match(/^(abbr|br|col|img|input|link|meta|param|hr|area|embed)$/i)?U:V+"></"+T+">"});var O=S.replace(/^\s+/,"").substring(0,10).toLowerCase();var Q=!O.indexOf("<opt")&&[1,"<select multiple='multiple'>","</select>"]||!O.indexOf("<leg")&&[1,"<fieldset>","</fieldset>"]||O.match(/^<(thead|tbody|tfoot|colg|cap)/)&&[1,"<table>","</table>"]||!O.indexOf("<tr")&&[2,"<table><tbody>","</tbody></table>"]||(!O.indexOf("<td")||!O.indexOf("<th"))&&[3,"<table><tbody><tr>","</tr></tbody></table>"]||!O.indexOf("<col")&&[2,"<table><tbody></tbody><colgroup>","</colgroup></table>"]||!o.support.htmlSerialize&&[1,"div<div>","</div>"]||[0,"",""];L.innerHTML=Q[1]+S+Q[2];while(Q[0]--){L=L.lastChild}if(!o.support.tbody){var R=/<tbody/i.test(S),N=!O.indexOf("<table")&&!R?L.firstChild&&L.firstChild.childNodes:Q[1]=="<table>"&&!R?L.childNodes:[];for(var M=N.length-1;M>=0;--M){if(o.nodeName(N[M],"tbody")&&!N[M].childNodes.length){N[M].parentNode.removeChild(N[M])}}}if(!o.support.leadingWhitespace&&/^\s/.test(S)){L.insertBefore(K.createTextNode(S.match(/^\s*/)[0]),L.firstChild)}S=o.makeArray(L.childNodes)}if(S.nodeType){G.push(S)}else{G=o.merge(G,S)}});if(I){for(var J=0;G[J];J++){if(o.nodeName(G[J],"script")&&(!G[J].type||G[J].type.toLowerCase()==="text/javascript")){E.push(G[J].parentNode?G[J].parentNode.removeChild(G[J]):G[J])}else{if(G[J].nodeType===1){G.splice.apply(G,[J+1,0].concat(o.makeArray(G[J].getElementsByTagName("script"))))}I.appendChild(G[J])}}return E}return G},attr:function(J,G,K){if(!J||J.nodeType==3||J.nodeType==8){return g}var H=!o.isXMLDoc(J),L=K!==g;G=H&&o.props[G]||G;if(J.tagName){var F=/href|src|style/.test(G);if(G=="selected"&&J.parentNode){J.parentNode.selectedIndex}if(G in J&&H&&!F){if(L){if(G=="type"&&o.nodeName(J,"input")&&J.parentNode){throw"type property can't be changed"}J[G]=K}if(o.nodeName(J,"form")&&J.getAttributeNode(G)){return J.getAttributeNode(G).nodeValue}if(G=="tabIndex"){var I=J.getAttributeNode("tabIndex");return I&&I.specified?I.value:J.nodeName.match(/(button|input|object|select|textarea)/i)?0:J.nodeName.match(/^(a|area)$/i)&&J.href?0:g}return J[G]}if(!o.support.style&&H&&G=="style"){return o.attr(J.style,"cssText",K)}if(L){J.setAttribute(G,""+K)}var E=!o.support.hrefNormalized&&H&&F?J.getAttribute(G,2):J.getAttribute(G);return E===null?g:E}if(!o.support.opacity&&G=="opacity"){if(L){J.zoom=1;J.filter=(J.filter||"").replace(/alpha\([^)]*\)/,"")+(parseInt(K)+""=="NaN"?"":"alpha(opacity="+K*100+")")}return J.filter&&J.filter.indexOf("opacity=")>=0?(parseFloat(J.filter.match(/opacity=([^)]*)/)[1])/100)+"":""}G=G.replace(/-([a-z])/ig,function(M,N){return N.toUpperCase()});if(L){J[G]=K}return J[G]},trim:function(E){return(E||"").replace(/^\s+|\s+$/g,"")},makeArray:function(G){var E=[];if(G!=null){var F=G.length;if(F==null||typeof G==="string"||o.isFunction(G)||G.setInterval){E[0]=G}else{while(F){E[--F]=G[F]}}}return E},inArray:function(G,H){for(var E=0,F=H.length;E<F;E++){if(H[E]===G){return E}}return -1},merge:function(H,E){var F=0,G,I=H.length;if(!o.support.getAll){while((G=E[F++])!=null){if(G.nodeType!=8){H[I++]=G}}}else{while((G=E[F++])!=null){H[I++]=G}}return H},unique:function(K){var F=[],E={};try{for(var G=0,H=K.length;G<H;G++){var J=o.data(K[G]);if(!E[J]){E[J]=true;F.push(K[G])}}}catch(I){F=K}return F},grep:function(F,J,E){var G=[];for(var H=0,I=F.length;H<I;H++){if(!E!=!J(F[H],H)){G.push(F[H])}}return G},map:function(E,J){var F=[];for(var G=0,H=E.length;G<H;G++){var I=J(E[G],G);if(I!=null){F[F.length]=I}}return F.concat.apply([],F)}});var C=navigator.userAgent.toLowerCase();o.browser={version:(C.match(/.+(?:rv|it|ra|ie)[\/: ]([\d.]+)/)||[0,"0"])[1],safari:/webkit/.test(C),opera:/opera/.test(C),msie:/msie/.test(C)&&!/opera/.test(C),mozilla:/mozilla/.test(C)&&!/(compatible|webkit)/.test(C)};o.each({parent:function(E){return E.parentNode},parents:function(E){return o.dir(E,"parentNode")},next:function(E){return o.nth(E,2,"nextSibling")},prev:function(E){return o.nth(E,2,"previousSibling")},nextAll:function(E){return o.dir(E,"nextSibling")},prevAll:function(E){return o.dir(E,"previousSibling")},siblings:function(E){return o.sibling(E.parentNode.firstChild,E)},children:function(E){return o.sibling(E.firstChild)},contents:function(E){return o.nodeName(E,"iframe")?E.contentDocument||E.contentWindow.document:o.makeArray(E.childNodes)}},function(E,F){o.fn[E]=function(G){var H=o.map(this,F);if(G&&typeof G=="string"){H=o.multiFilter(G,H)}return this.pushStack(o.unique(H),E,G)}});o.each({appendTo:"append",prependTo:"prepend",insertBefore:"before",insertAfter:"after",replaceAll:"replaceWith"},function(E,F){o.fn[E]=function(G){var J=[],L=o(G);for(var K=0,H=L.length;K<H;K++){var I=(K>0?this.clone(true):this).get();o.fn[F].apply(o(L[K]),I);J=J.concat(I)}return this.pushStack(J,E,G)}});o.each({removeAttr:function(E){o.attr(this,E,"");if(this.nodeType==1){this.removeAttribute(E)}},addClass:function(E){o.className.add(this,E)},removeClass:function(E){o.className.remove(this,E)},toggleClass:function(F,E){if(typeof E!=="boolean"){E=!o.className.has(this,F)}o.className[E?"add":"remove"](this,F)},remove:function(E){if(!E||o.filter(E,[this]).length){o("*",this).add([this]).each(function(){o.event.remove(this);o.removeData(this)});if(this.parentNode){this.parentNode.removeChild(this)}}},empty:function(){o(this).children().remove();while(this.firstChild){this.removeChild(this.firstChild)}}},function(E,F){o.fn[E]=function(){return this.each(F,arguments)}});function j(E,F){return E[0]&&parseInt(o.curCSS(E[0],F,true),10)||0}var h="jQuery"+e(),v=0,A={};o.extend({cache:{},data:function(F,E,G){F=F==l?A:F;var H=F[h];if(!H){H=F[h]=++v}if(E&&!o.cache[H]){o.cache[H]={}}if(G!==g){o.cache[H][E]=G}return E?o.cache[H][E]:H},removeData:function(F,E){F=F==l?A:F;var H=F[h];if(E){if(o.cache[H]){delete o.cache[H][E];E="";for(E in o.cache[H]){break}if(!E){o.removeData(F)}}}else{try{delete F[h]}catch(G){if(F.removeAttribute){F.removeAttribute(h)}}delete o.cache[H]}},queue:function(F,E,H){if(F){E=(E||"fx")+"queue";var G=o.data(F,E);if(!G||o.isArray(H)){G=o.data(F,E,o.makeArray(H))}else{if(H){G.push(H)}}}return G},dequeue:function(H,G){var E=o.queue(H,G),F=E.shift();if(!G||G==="fx"){F=E[0]}if(F!==g){F.call(H)}}});o.fn.extend({data:function(E,G){var H=E.split(".");H[1]=H[1]?"."+H[1]:"";if(G===g){var F=this.triggerHandler("getData"+H[1]+"!",[H[0]]);if(F===g&&this.length){F=o.data(this[0],E)}return F===g&&H[1]?this.data(H[0]):F}else{return this.trigger("setData"+H[1]+"!",[H[0],G]).each(function(){o.data(this,E,G)})}},removeData:function(E){return this.each(function(){o.removeData(this,E)})},queue:function(E,F){if(typeof E!=="string"){F=E;E="fx"}if(F===g){return o.queue(this[0],E)}return this.each(function(){var G=o.queue(this,E,F);if(E=="fx"&&G.length==1){G[0].call(this)}})},dequeue:function(E){return this.each(function(){o.dequeue(this,E)})}});
/*
 * Sizzle CSS Selector Engine - v0.9.3
 *  Copyright 2009, The Dojo Foundation
 *  Released under the MIT, BSD, and GPL Licenses.
 *  More information: http://sizzlejs.com/
 */
(function(){var R=/((?:\((?:\([^()]+\)|[^()]+)+\)|\[(?:\[[^[\]]*\]|['"][^'"]*['"]|[^[\]'"]+)+\]|\\.|[^ >+~,(\[\\]+)+|[>+~])(\s*,\s*)?/g,L=0,H=Object.prototype.toString;var F=function(Y,U,ab,ac){ab=ab||[];U=U||document;if(U.nodeType!==1&&U.nodeType!==9){return[]}if(!Y||typeof Y!=="string"){return ab}var Z=[],W,af,ai,T,ad,V,X=true;R.lastIndex=0;while((W=R.exec(Y))!==null){Z.push(W[1]);if(W[2]){V=RegExp.rightContext;break}}if(Z.length>1&&M.exec(Y)){if(Z.length===2&&I.relative[Z[0]]){af=J(Z[0]+Z[1],U)}else{af=I.relative[Z[0]]?[U]:F(Z.shift(),U);while(Z.length){Y=Z.shift();if(I.relative[Y]){Y+=Z.shift()}af=J(Y,af)}}}else{var ae=ac?{expr:Z.pop(),set:E(ac)}:F.find(Z.pop(),Z.length===1&&U.parentNode?U.parentNode:U,Q(U));af=F.filter(ae.expr,ae.set);if(Z.length>0){ai=E(af)}else{X=false}while(Z.length){var ah=Z.pop(),ag=ah;if(!I.relative[ah]){ah=""}else{ag=Z.pop()}if(ag==null){ag=U}I.relative[ah](ai,ag,Q(U))}}if(!ai){ai=af}if(!ai){throw"Syntax error, unrecognized expression: "+(ah||Y)}if(H.call(ai)==="[object Array]"){if(!X){ab.push.apply(ab,ai)}else{if(U.nodeType===1){for(var aa=0;ai[aa]!=null;aa++){if(ai[aa]&&(ai[aa]===true||ai[aa].nodeType===1&&K(U,ai[aa]))){ab.push(af[aa])}}}else{for(var aa=0;ai[aa]!=null;aa++){if(ai[aa]&&ai[aa].nodeType===1){ab.push(af[aa])}}}}}else{E(ai,ab)}if(V){F(V,U,ab,ac);if(G){hasDuplicate=false;ab.sort(G);if(hasDuplicate){for(var aa=1;aa<ab.length;aa++){if(ab[aa]===ab[aa-1]){ab.splice(aa--,1)}}}}}return ab};F.matches=function(T,U){return F(T,null,null,U)};F.find=function(aa,T,ab){var Z,X;if(!aa){return[]}for(var W=0,V=I.order.length;W<V;W++){var Y=I.order[W],X;if((X=I.match[Y].exec(aa))){var U=RegExp.leftContext;if(U.substr(U.length-1)!=="\\"){X[1]=(X[1]||"").replace(/\\/g,"");Z=I.find[Y](X,T,ab);if(Z!=null){aa=aa.replace(I.match[Y],"");break}}}}if(!Z){Z=T.getElementsByTagName("*")}return{set:Z,expr:aa}};F.filter=function(ad,ac,ag,W){var V=ad,ai=[],aa=ac,Y,T,Z=ac&&ac[0]&&Q(ac[0]);while(ad&&ac.length){for(var ab in I.filter){if((Y=I.match[ab].exec(ad))!=null){var U=I.filter[ab],ah,af;T=false;if(aa==ai){ai=[]}if(I.preFilter[ab]){Y=I.preFilter[ab](Y,aa,ag,ai,W,Z);if(!Y){T=ah=true}else{if(Y===true){continue}}}if(Y){for(var X=0;(af=aa[X])!=null;X++){if(af){ah=U(af,Y,X,aa);var ae=W^!!ah;if(ag&&ah!=null){if(ae){T=true}else{aa[X]=false}}else{if(ae){ai.push(af);T=true}}}}}if(ah!==g){if(!ag){aa=ai}ad=ad.replace(I.match[ab],"");if(!T){return[]}break}}}if(ad==V){if(T==null){throw"Syntax error, unrecognized expression: "+ad}else{break}}V=ad}return aa};var I=F.selectors={order:["ID","NAME","TAG"],match:{ID:/#((?:[\w\u00c0-\uFFFF_-]|\\.)+)/,CLASS:/\.((?:[\w\u00c0-\uFFFF_-]|\\.)+)/,NAME:/\[name=['"]*((?:[\w\u00c0-\uFFFF_-]|\\.)+)['"]*\]/,ATTR:/\[\s*((?:[\w\u00c0-\uFFFF_-]|\\.)+)\s*(?:(\S?=)\s*(['"]*)(.*?)\3|)\s*\]/,TAG:/^((?:[\w\u00c0-\uFFFF\*_-]|\\.)+)/,CHILD:/:(only|nth|last|first)-child(?:\((even|odd|[\dn+-]*)\))?/,POS:/:(nth|eq|gt|lt|first|last|even|odd)(?:\((\d*)\))?(?=[^-]|$)/,PSEUDO:/:((?:[\w\u00c0-\uFFFF_-]|\\.)+)(?:\((['"]*)((?:\([^\)]+\)|[^\2\(\)]*)+)\2\))?/},attrMap:{"class":"className","for":"htmlFor"},attrHandle:{href:function(T){return T.getAttribute("href")}},relative:{"+":function(aa,T,Z){var X=typeof T==="string",ab=X&&!/\W/.test(T),Y=X&&!ab;if(ab&&!Z){T=T.toUpperCase()}for(var W=0,V=aa.length,U;W<V;W++){if((U=aa[W])){while((U=U.previousSibling)&&U.nodeType!==1){}aa[W]=Y||U&&U.nodeName===T?U||false:U===T}}if(Y){F.filter(T,aa,true)}},">":function(Z,U,aa){var X=typeof U==="string";if(X&&!/\W/.test(U)){U=aa?U:U.toUpperCase();for(var V=0,T=Z.length;V<T;V++){var Y=Z[V];if(Y){var W=Y.parentNode;Z[V]=W.nodeName===U?W:false}}}else{for(var V=0,T=Z.length;V<T;V++){var Y=Z[V];if(Y){Z[V]=X?Y.parentNode:Y.parentNode===U}}if(X){F.filter(U,Z,true)}}},"":function(W,U,Y){var V=L++,T=S;if(!U.match(/\W/)){var X=U=Y?U:U.toUpperCase();T=P}T("parentNode",U,V,W,X,Y)},"~":function(W,U,Y){var V=L++,T=S;if(typeof U==="string"&&!U.match(/\W/)){var X=U=Y?U:U.toUpperCase();T=P}T("previousSibling",U,V,W,X,Y)}},find:{ID:function(U,V,W){if(typeof V.getElementById!=="undefined"&&!W){var T=V.getElementById(U[1]);return T?[T]:[]}},NAME:function(V,Y,Z){if(typeof Y.getElementsByName!=="undefined"){var U=[],X=Y.getElementsByName(V[1]);for(var W=0,T=X.length;W<T;W++){if(X[W].getAttribute("name")===V[1]){U.push(X[W])}}return U.length===0?null:U}},TAG:function(T,U){return U.getElementsByTagName(T[1])}},preFilter:{CLASS:function(W,U,V,T,Z,aa){W=" "+W[1].replace(/\\/g,"")+" ";if(aa){return W}for(var X=0,Y;(Y=U[X])!=null;X++){if(Y){if(Z^(Y.className&&(" "+Y.className+" ").indexOf(W)>=0)){if(!V){T.push(Y)}}else{if(V){U[X]=false}}}}return false},ID:function(T){return T[1].replace(/\\/g,"")},TAG:function(U,T){for(var V=0;T[V]===false;V++){}return T[V]&&Q(T[V])?U[1]:U[1].toUpperCase()},CHILD:function(T){if(T[1]=="nth"){var U=/(-?)(\d*)n((?:\+|-)?\d*)/.exec(T[2]=="even"&&"2n"||T[2]=="odd"&&"2n+1"||!/\D/.test(T[2])&&"0n+"+T[2]||T[2]);T[2]=(U[1]+(U[2]||1))-0;T[3]=U[3]-0}T[0]=L++;return T},ATTR:function(X,U,V,T,Y,Z){var W=X[1].replace(/\\/g,"");if(!Z&&I.attrMap[W]){X[1]=I.attrMap[W]}if(X[2]==="~="){X[4]=" "+X[4]+" "}return X},PSEUDO:function(X,U,V,T,Y){if(X[1]==="not"){if(X[3].match(R).length>1||/^\w/.test(X[3])){X[3]=F(X[3],null,null,U)}else{var W=F.filter(X[3],U,V,true^Y);if(!V){T.push.apply(T,W)}return false}}else{if(I.match.POS.test(X[0])||I.match.CHILD.test(X[0])){return true}}return X},POS:function(T){T.unshift(true);return T}},filters:{enabled:function(T){return T.disabled===false&&T.type!=="hidden"},disabled:function(T){return T.disabled===true},checked:function(T){return T.checked===true},selected:function(T){T.parentNode.selectedIndex;return T.selected===true},parent:function(T){return !!T.firstChild},empty:function(T){return !T.firstChild},has:function(V,U,T){return !!F(T[3],V).length},header:function(T){return/h\d/i.test(T.nodeName)},text:function(T){return"text"===T.type},radio:function(T){return"radio"===T.type},checkbox:function(T){return"checkbox"===T.type},file:function(T){return"file"===T.type},password:function(T){return"password"===T.type},submit:function(T){return"submit"===T.type},image:function(T){return"image"===T.type},reset:function(T){return"reset"===T.type},button:function(T){return"button"===T.type||T.nodeName.toUpperCase()==="BUTTON"},input:function(T){return/input|select|textarea|button/i.test(T.nodeName)}},setFilters:{first:function(U,T){return T===0},last:function(V,U,T,W){return U===W.length-1},even:function(U,T){return T%2===0},odd:function(U,T){return T%2===1},lt:function(V,U,T){return U<T[3]-0},gt:function(V,U,T){return U>T[3]-0},nth:function(V,U,T){return T[3]-0==U},eq:function(V,U,T){return T[3]-0==U}},filter:{PSEUDO:function(Z,V,W,aa){var U=V[1],X=I.filters[U];if(X){return X(Z,W,V,aa)}else{if(U==="contains"){return(Z.textContent||Z.innerText||"").indexOf(V[3])>=0}else{if(U==="not"){var Y=V[3];for(var W=0,T=Y.length;W<T;W++){if(Y[W]===Z){return false}}return true}}}},CHILD:function(T,W){var Z=W[1],U=T;switch(Z){case"only":case"first":while(U=U.previousSibling){if(U.nodeType===1){return false}}if(Z=="first"){return true}U=T;case"last":while(U=U.nextSibling){if(U.nodeType===1){return false}}return true;case"nth":var V=W[2],ac=W[3];if(V==1&&ac==0){return true}var Y=W[0],ab=T.parentNode;if(ab&&(ab.sizcache!==Y||!T.nodeIndex)){var X=0;for(U=ab.firstChild;U;U=U.nextSibling){if(U.nodeType===1){U.nodeIndex=++X}}ab.sizcache=Y}var aa=T.nodeIndex-ac;if(V==0){return aa==0}else{return(aa%V==0&&aa/V>=0)}}},ID:function(U,T){return U.nodeType===1&&U.getAttribute("id")===T},TAG:function(U,T){return(T==="*"&&U.nodeType===1)||U.nodeName===T},CLASS:function(U,T){return(" "+(U.className||U.getAttribute("class"))+" ").indexOf(T)>-1},ATTR:function(Y,W){var V=W[1],T=I.attrHandle[V]?I.attrHandle[V](Y):Y[V]!=null?Y[V]:Y.getAttribute(V),Z=T+"",X=W[2],U=W[4];return T==null?X==="!=":X==="="?Z===U:X==="*="?Z.indexOf(U)>=0:X==="~="?(" "+Z+" ").indexOf(U)>=0:!U?Z&&T!==false:X==="!="?Z!=U:X==="^="?Z.indexOf(U)===0:X==="$="?Z.substr(Z.length-U.length)===U:X==="|="?Z===U||Z.substr(0,U.length+1)===U+"-":false},POS:function(X,U,V,Y){var T=U[2],W=I.setFilters[T];if(W){return W(X,V,U,Y)}}}};var M=I.match.POS;for(var O in I.match){I.match[O]=RegExp(I.match[O].source+/(?![^\[]*\])(?![^\(]*\))/.source)}var E=function(U,T){U=Array.prototype.slice.call(U);if(T){T.push.apply(T,U);return T}return U};try{Array.prototype.slice.call(document.documentElement.childNodes)}catch(N){E=function(X,W){var U=W||[];if(H.call(X)==="[object Array]"){Array.prototype.push.apply(U,X)}else{if(typeof X.length==="number"){for(var V=0,T=X.length;V<T;V++){U.push(X[V])}}else{for(var V=0;X[V];V++){U.push(X[V])}}}return U}}var G;if(document.documentElement.compareDocumentPosition){G=function(U,T){var V=U.compareDocumentPosition(T)&4?-1:U===T?0:1;if(V===0){hasDuplicate=true}return V}}else{if("sourceIndex" in document.documentElement){G=function(U,T){var V=U.sourceIndex-T.sourceIndex;if(V===0){hasDuplicate=true}return V}}else{if(document.createRange){G=function(W,U){var V=W.ownerDocument.createRange(),T=U.ownerDocument.createRange();V.selectNode(W);V.collapse(true);T.selectNode(U);T.collapse(true);var X=V.compareBoundaryPoints(Range.START_TO_END,T);if(X===0){hasDuplicate=true}return X}}}}(function(){var U=document.createElement("form"),V="script"+(new Date).getTime();U.innerHTML="<input name='"+V+"'/>";var T=document.documentElement;T.insertBefore(U,T.firstChild);if(!!document.getElementById(V)){I.find.ID=function(X,Y,Z){if(typeof Y.getElementById!=="undefined"&&!Z){var W=Y.getElementById(X[1]);return W?W.id===X[1]||typeof W.getAttributeNode!=="undefined"&&W.getAttributeNode("id").nodeValue===X[1]?[W]:g:[]}};I.filter.ID=function(Y,W){var X=typeof Y.getAttributeNode!=="undefined"&&Y.getAttributeNode("id");return Y.nodeType===1&&X&&X.nodeValue===W}}T.removeChild(U)})();(function(){var T=document.createElement("div");T.appendChild(document.createComment(""));if(T.getElementsByTagName("*").length>0){I.find.TAG=function(U,Y){var X=Y.getElementsByTagName(U[1]);if(U[1]==="*"){var W=[];for(var V=0;X[V];V++){if(X[V].nodeType===1){W.push(X[V])}}X=W}return X}}T.innerHTML="<a href='#'></a>";if(T.firstChild&&typeof T.firstChild.getAttribute!=="undefined"&&T.firstChild.getAttribute("href")!=="#"){I.attrHandle.href=function(U){return U.getAttribute("href",2)}}})();if(document.querySelectorAll){(function(){var T=F,U=document.createElement("div");U.innerHTML="<p class='TEST'></p>";if(U.querySelectorAll&&U.querySelectorAll(".TEST").length===0){return}F=function(Y,X,V,W){X=X||document;if(!W&&X.nodeType===9&&!Q(X)){try{return E(X.querySelectorAll(Y),V)}catch(Z){}}return T(Y,X,V,W)};F.find=T.find;F.filter=T.filter;F.selectors=T.selectors;F.matches=T.matches})()}if(document.getElementsByClassName&&document.documentElement.getElementsByClassName){(function(){var T=document.createElement("div");T.innerHTML="<div class='test e'></div><div class='test'></div>";if(T.getElementsByClassName("e").length===0){return}T.lastChild.className="e";if(T.getElementsByClassName("e").length===1){return}I.order.splice(1,0,"CLASS");I.find.CLASS=function(U,V,W){if(typeof V.getElementsByClassName!=="undefined"&&!W){return V.getElementsByClassName(U[1])}}})()}function P(U,Z,Y,ad,aa,ac){var ab=U=="previousSibling"&&!ac;for(var W=0,V=ad.length;W<V;W++){var T=ad[W];if(T){if(ab&&T.nodeType===1){T.sizcache=Y;T.sizset=W}T=T[U];var X=false;while(T){if(T.sizcache===Y){X=ad[T.sizset];break}if(T.nodeType===1&&!ac){T.sizcache=Y;T.sizset=W}if(T.nodeName===Z){X=T;break}T=T[U]}ad[W]=X}}}function S(U,Z,Y,ad,aa,ac){var ab=U=="previousSibling"&&!ac;for(var W=0,V=ad.length;W<V;W++){var T=ad[W];if(T){if(ab&&T.nodeType===1){T.sizcache=Y;T.sizset=W}T=T[U];var X=false;while(T){if(T.sizcache===Y){X=ad[T.sizset];break}if(T.nodeType===1){if(!ac){T.sizcache=Y;T.sizset=W}if(typeof Z!=="string"){if(T===Z){X=true;break}}else{if(F.filter(Z,[T]).length>0){X=T;break}}}T=T[U]}ad[W]=X}}}var K=document.compareDocumentPosition?function(U,T){return U.compareDocumentPosition(T)&16}:function(U,T){return U!==T&&(U.contains?U.contains(T):true)};var Q=function(T){return T.nodeType===9&&T.documentElement.nodeName!=="HTML"||!!T.ownerDocument&&Q(T.ownerDocument)};var J=function(T,aa){var W=[],X="",Y,V=aa.nodeType?[aa]:aa;while((Y=I.match.PSEUDO.exec(T))){X+=Y[0];T=T.replace(I.match.PSEUDO,"")}T=I.relative[T]?T+"*":T;for(var Z=0,U=V.length;Z<U;Z++){F(T,V[Z],W)}return F.filter(X,W)};o.find=F;o.filter=F.filter;o.expr=F.selectors;o.expr[":"]=o.expr.filters;F.selectors.filters.hidden=function(T){return T.offsetWidth===0||T.offsetHeight===0};F.selectors.filters.visible=function(T){return T.offsetWidth>0||T.offsetHeight>0};F.selectors.filters.animated=function(T){return o.grep(o.timers,function(U){return T===U.elem}).length};o.multiFilter=function(V,T,U){if(U){V=":not("+V+")"}return F.matches(V,T)};o.dir=function(V,U){var T=[],W=V[U];while(W&&W!=document){if(W.nodeType==1){T.push(W)}W=W[U]}return T};o.nth=function(X,T,V,W){T=T||1;var U=0;for(;X;X=X[V]){if(X.nodeType==1&&++U==T){break}}return X};o.sibling=function(V,U){var T=[];for(;V;V=V.nextSibling){if(V.nodeType==1&&V!=U){T.push(V)}}return T};return;l.Sizzle=F})();o.event={add:function(I,F,H,K){if(I.nodeType==3||I.nodeType==8){return}if(I.setInterval&&I!=l){I=l}if(!H.guid){H.guid=this.guid++}if(K!==g){var G=H;H=this.proxy(G);H.data=K}var E=o.data(I,"events")||o.data(I,"events",{}),J=o.data(I,"handle")||o.data(I,"handle",function(){return typeof o!=="undefined"&&!o.event.triggered?o.event.handle.apply(arguments.callee.elem,arguments):g});J.elem=I;o.each(F.split(/\s+/),function(M,N){var O=N.split(".");N=O.shift();H.type=O.slice().sort().join(".");var L=E[N];if(o.event.specialAll[N]){o.event.specialAll[N].setup.call(I,K,O)}if(!L){L=E[N]={};if(!o.event.special[N]||o.event.special[N].setup.call(I,K,O)===false){if(I.addEventListener){I.addEventListener(N,J,false)}else{if(I.attachEvent){I.attachEvent("on"+N,J)}}}}L[H.guid]=H;o.event.global[N]=true});I=null},guid:1,global:{},remove:function(K,H,J){if(K.nodeType==3||K.nodeType==8){return}var G=o.data(K,"events"),F,E;if(G){if(H===g||(typeof H==="string"&&H.charAt(0)==".")){for(var I in G){this.remove(K,I+(H||""))}}else{if(H.type){J=H.handler;H=H.type}o.each(H.split(/\s+/),function(M,O){var Q=O.split(".");O=Q.shift();var N=RegExp("(^|\\.)"+Q.slice().sort().join(".*\\.")+"(\\.|$)");if(G[O]){if(J){delete G[O][J.guid]}else{for(var P in G[O]){if(N.test(G[O][P].type)){delete G[O][P]}}}if(o.event.specialAll[O]){o.event.specialAll[O].teardown.call(K,Q)}for(F in G[O]){break}if(!F){if(!o.event.special[O]||o.event.special[O].teardown.call(K,Q)===false){if(K.removeEventListener){K.removeEventListener(O,o.data(K,"handle"),false)}else{if(K.detachEvent){K.detachEvent("on"+O,o.data(K,"handle"))}}}F=null;delete G[O]}}})}for(F in G){break}if(!F){var L=o.data(K,"handle");if(L){L.elem=null}o.removeData(K,"events");o.removeData(K,"handle")}}},trigger:function(I,K,H,E){var G=I.type||I;if(!E){I=typeof I==="object"?I[h]?I:o.extend(o.Event(G),I):o.Event(G);if(G.indexOf("!")>=0){I.type=G=G.slice(0,-1);I.exclusive=true}if(!H){I.stopPropagation();if(this.global[G]){o.each(o.cache,function(){if(this.events&&this.events[G]){o.event.trigger(I,K,this.handle.elem)}})}}if(!H||H.nodeType==3||H.nodeType==8){return g}I.result=g;I.target=H;K=o.makeArray(K);K.unshift(I)}I.currentTarget=H;var J=o.data(H,"handle");if(J){J.apply(H,K)}if((!H[G]||(o.nodeName(H,"a")&&G=="click"))&&H["on"+G]&&H["on"+G].apply(H,K)===false){I.result=false}if(!E&&H[G]&&!I.isDefaultPrevented()&&!(o.nodeName(H,"a")&&G=="click")){this.triggered=true;try{H[G]()}catch(L){}}this.triggered=false;if(!I.isPropagationStopped()){var F=H.parentNode||H.ownerDocument;if(F){o.event.trigger(I,K,F,true)}}},handle:function(K){var J,E;K=arguments[0]=o.event.fix(K||l.event);K.currentTarget=this;var L=K.type.split(".");K.type=L.shift();J=!L.length&&!K.exclusive;var I=RegExp("(^|\\.)"+L.slice().sort().join(".*\\.")+"(\\.|$)");E=(o.data(this,"events")||{})[K.type];for(var G in E){var H=E[G];if(J||I.test(H.type)){K.handler=H;K.data=H.data;var F=H.apply(this,arguments);if(F!==g){K.result=F;if(F===false){K.preventDefault();K.stopPropagation()}}if(K.isImmediatePropagationStopped()){break}}}},props:"altKey attrChange attrName bubbles button cancelable charCode clientX clientY ctrlKey currentTarget data detail eventPhase fromElement handler keyCode metaKey newValue originalTarget pageX pageY prevValue relatedNode relatedTarget screenX screenY shiftKey srcElement target toElement view wheelDelta which".split(" "),fix:function(H){if(H[h]){return H}var F=H;H=o.Event(F);for(var G=this.props.length,J;G;){J=this.props[--G];H[J]=F[J]}if(!H.target){H.target=H.srcElement||document}if(H.target.nodeType==3){H.target=H.target.parentNode}if(!H.relatedTarget&&H.fromElement){H.relatedTarget=H.fromElement==H.target?H.toElement:H.fromElement}if(H.pageX==null&&H.clientX!=null){var I=document.documentElement,E=document.body;H.pageX=H.clientX+(I&&I.scrollLeft||E&&E.scrollLeft||0)-(I.clientLeft||0);H.pageY=H.clientY+(I&&I.scrollTop||E&&E.scrollTop||0)-(I.clientTop||0)}if(!H.which&&((H.charCode||H.charCode===0)?H.charCode:H.keyCode)){H.which=H.charCode||H.keyCode}if(!H.metaKey&&H.ctrlKey){H.metaKey=H.ctrlKey}if(!H.which&&H.button){H.which=(H.button&1?1:(H.button&2?3:(H.button&4?2:0)))}return H},proxy:function(F,E){E=E||function(){return F.apply(this,arguments)};E.guid=F.guid=F.guid||E.guid||this.guid++;return E},special:{ready:{setup:B,teardown:function(){}}},specialAll:{live:{setup:function(E,F){o.event.add(this,F[0],c)},teardown:function(G){if(G.length){var E=0,F=RegExp("(^|\\.)"+G[0]+"(\\.|$)");o.each((o.data(this,"events").live||{}),function(){if(F.test(this.type)){E++}});if(E<1){o.event.remove(this,G[0],c)}}}}}};o.Event=function(E){if(!this.preventDefault){return new o.Event(E)}if(E&&E.type){this.originalEvent=E;this.type=E.type}else{this.type=E}this.timeStamp=e();this[h]=true};function k(){return false}function u(){return true}o.Event.prototype={preventDefault:function(){this.isDefaultPrevented=u;var E=this.originalEvent;if(!E){return}if(E.preventDefault){E.preventDefault()}E.returnValue=false},stopPropagation:function(){this.isPropagationStopped=u;var E=this.originalEvent;if(!E){return}if(E.stopPropagation){E.stopPropagation()}E.cancelBubble=true},stopImmediatePropagation:function(){this.isImmediatePropagationStopped=u;this.stopPropagation()},isDefaultPrevented:k,isPropagationStopped:k,isImmediatePropagationStopped:k};var a=function(F){var E=F.relatedTarget;while(E&&E!=this){try{E=E.parentNode}catch(G){E=this}}if(E!=this){F.type=F.data;o.event.handle.apply(this,arguments)}};o.each({mouseover:"mouseenter",mouseout:"mouseleave"},function(F,E){o.event.special[E]={setup:function(){o.event.add(this,F,a,E)},teardown:function(){o.event.remove(this,F,a)}}});o.fn.extend({bind:function(F,G,E){return F=="unload"?this.one(F,G,E):this.each(function(){o.event.add(this,F,E||G,E&&G)})},one:function(G,H,F){var E=o.event.proxy(F||H,function(I){o(this).unbind(I,E);return(F||H).apply(this,arguments)});return this.each(function(){o.event.add(this,G,E,F&&H)})},unbind:function(F,E){return this.each(function(){o.event.remove(this,F,E)})},trigger:function(E,F){return this.each(function(){o.event.trigger(E,F,this)})},triggerHandler:function(E,G){if(this[0]){var F=o.Event(E);F.preventDefault();F.stopPropagation();o.event.trigger(F,G,this[0]);return F.result}},toggle:function(G){var E=arguments,F=1;while(F<E.length){o.event.proxy(G,E[F++])}return this.click(o.event.proxy(G,function(H){this.lastToggle=(this.lastToggle||0)%F;H.preventDefault();return E[this.lastToggle++].apply(this,arguments)||false}))},hover:function(E,F){return this.mouseenter(E).mouseleave(F)},ready:function(E){B();if(o.isReady){E.call(document,o)}else{o.readyList.push(E)}return this},live:function(G,F){var E=o.event.proxy(F);E.guid+=this.selector+G;o(document).bind(i(G,this.selector),this.selector,E);return this},die:function(F,E){o(document).unbind(i(F,this.selector),E?{guid:E.guid+this.selector+F}:null);return this}});function c(H){var E=RegExp("(^|\\.)"+H.type+"(\\.|$)"),G=true,F=[];o.each(o.data(this,"events").live||[],function(I,J){if(E.test(J.type)){var K=o(H.target).closest(J.data)[0];if(K){F.push({elem:K,fn:J})}}});F.sort(function(J,I){return o.data(J.elem,"closest")-o.data(I.elem,"closest")});o.each(F,function(){if(this.fn.call(this.elem,H,this.fn.data)===false){return(G=false)}});return G}function i(F,E){return["live",F,E.replace(/\./g,"`").replace(/ /g,"|")].join(".")}o.extend({isReady:false,readyList:[],ready:function(){if(!o.isReady){o.isReady=true;if(o.readyList){o.each(o.readyList,function(){this.call(document,o)});o.readyList=null}o(document).triggerHandler("ready")}}});var x=false;function B(){if(x){return}x=true;if(document.addEventListener){document.addEventListener("DOMContentLoaded",function(){document.removeEventListener("DOMContentLoaded",arguments.callee,false);o.ready()},false)}else{if(document.attachEvent){document.attachEvent("onreadystatechange",function(){if(document.readyState==="complete"){document.detachEvent("onreadystatechange",arguments.callee);o.ready()}});if(document.documentElement.doScroll&&l==l.top){(function(){if(o.isReady){return}try{document.documentElement.doScroll("left")}catch(E){setTimeout(arguments.callee,0);return}o.ready()})()}}}o.event.add(l,"load",o.ready)}o.each(("blur,focus,load,resize,scroll,unload,click,dblclick,mousedown,mouseup,mousemove,mouseover,mouseout,mouseenter,mouseleave,change,select,submit,keydown,keypress,keyup,error").split(","),function(F,E){o.fn[E]=function(G){return G?this.bind(E,G):this.trigger(E)}});o(l).bind("unload",function(){for(var E in o.cache){if(E!=1&&o.cache[E].handle){o.event.remove(o.cache[E].handle.elem)}}});(function(){o.support={};var F=document.documentElement,G=document.createElement("script"),K=document.createElement("div"),J="script"+(new Date).getTime();K.style.display="none";K.innerHTML='   <link/><table></table><a href="/a" style="color:red;float:left;opacity:.5;">a</a><select><option>text</option></select><object><param/></object>';var H=K.getElementsByTagName("*"),E=K.getElementsByTagName("a")[0];if(!H||!H.length||!E){return}o.support={leadingWhitespace:K.firstChild.nodeType==3,tbody:!K.getElementsByTagName("tbody").length,objectAll:!!K.getElementsByTagName("object")[0].getElementsByTagName("*").length,htmlSerialize:!!K.getElementsByTagName("link").length,style:/red/.test(E.getAttribute("style")),hrefNormalized:E.getAttribute("href")==="/a",opacity:E.style.opacity==="0.5",cssFloat:!!E.style.cssFloat,scriptEval:false,noCloneEvent:true,boxModel:null};G.type="text/javascript";try{G.appendChild(document.createTextNode("window."+J+"=1;"))}catch(I){}F.insertBefore(G,F.firstChild);if(l[J]){o.support.scriptEval=true;delete l[J]}F.removeChild(G);if(K.attachEvent&&K.fireEvent){K.attachEvent("onclick",function(){o.support.noCloneEvent=false;K.detachEvent("onclick",arguments.callee)});K.cloneNode(true).fireEvent("onclick")}o(function(){var L=document.createElement("div");L.style.width=L.style.paddingLeft="1px";document.body.appendChild(L);o.boxModel=o.support.boxModel=L.offsetWidth===2;document.body.removeChild(L).style.display="none"})})();var w=o.support.cssFloat?"cssFloat":"styleFloat";o.props={"for":"htmlFor","class":"className","float":w,cssFloat:w,styleFloat:w,readonly:"readOnly",maxlength:"maxLength",cellspacing:"cellSpacing",rowspan:"rowSpan",tabindex:"tabIndex"};o.fn.extend({_load:o.fn.load,load:function(G,J,K){if(typeof G!=="string"){return this._load(G)}var I=G.indexOf(" ");if(I>=0){var E=G.slice(I,G.length);G=G.slice(0,I)}var H="GET";if(J){if(o.isFunction(J)){K=J;J=null}else{if(typeof J==="object"){J=o.param(J);H="POST"}}}var F=this;o.ajax({url:G,type:H,dataType:"html",data:J,complete:function(M,L){if(L=="success"||L=="notmodified"){F.html(E?o("<div/>").append(M.responseText.replace(/<script(.|\s)*?\/script>/g,"")).find(E):M.responseText)}if(K){F.each(K,[M.responseText,L,M])}}});return this},serialize:function(){return o.param(this.serializeArray())},serializeArray:function(){return this.map(function(){return this.elements?o.makeArray(this.elements):this}).filter(function(){return this.name&&!this.disabled&&(this.checked||/select|textarea/i.test(this.nodeName)||/text|hidden|password|search/i.test(this.type))}).map(function(E,F){var G=o(this).val();return G==null?null:o.isArray(G)?o.map(G,function(I,H){return{name:F.name,value:I}}):{name:F.name,value:G}}).get()}});o.each("ajaxStart,ajaxStop,ajaxComplete,ajaxError,ajaxSuccess,ajaxSend".split(","),function(E,F){o.fn[F]=function(G){return this.bind(F,G)}});var r=e();o.extend({get:function(E,G,H,F){if(o.isFunction(G)){H=G;G=null}return o.ajax({type:"GET",url:E,data:G,success:H,dataType:F})},getScript:function(E,F){return o.get(E,null,F,"script")},getJSON:function(E,F,G){return o.get(E,F,G,"json")},post:function(E,G,H,F){if(o.isFunction(G)){H=G;G={}}return o.ajax({type:"POST",url:E,data:G,success:H,dataType:F})},ajaxSetup:function(E){o.extend(o.ajaxSettings,E)},ajaxSettings:{url:location.href,global:true,type:"GET",contentType:"application/x-www-form-urlencoded",processData:true,async:true,xhr:function(){return l.ActiveXObject?new ActiveXObject("Microsoft.XMLHTTP"):new XMLHttpRequest()},accepts:{xml:"application/xml, text/xml",html:"text/html",script:"text/javascript, application/javascript",json:"application/json, text/javascript",text:"text/plain",_default:"*/*"}},lastModified:{},ajax:function(M){M=o.extend(true,M,o.extend(true,{},o.ajaxSettings,M));var W,F=/=\?(&|$)/g,R,V,G=M.type.toUpperCase();if(M.data&&M.processData&&typeof M.data!=="string"){M.data=o.param(M.data)}if(M.dataType=="jsonp"){if(G=="GET"){if(!M.url.match(F)){M.url+=(M.url.match(/\?/)?"&":"?")+(M.jsonp||"callback")+"=?"}}else{if(!M.data||!M.data.match(F)){M.data=(M.data?M.data+"&":"")+(M.jsonp||"callback")+"=?"}}M.dataType="json"}if(M.dataType=="json"&&(M.data&&M.data.match(F)||M.url.match(F))){W="jsonp"+r++;if(M.data){M.data=(M.data+"").replace(F,"="+W+"$1")}M.url=M.url.replace(F,"="+W+"$1");M.dataType="script";l[W]=function(X){V=X;I();L();l[W]=g;try{delete l[W]}catch(Y){}if(H){H.removeChild(T)}}}if(M.dataType=="script"&&M.cache==null){M.cache=false}if(M.cache===false&&G=="GET"){var E=e();var U=M.url.replace(/(\?|&)_=.*?(&|$)/,"$1_="+E+"$2");M.url=U+((U==M.url)?(M.url.match(/\?/)?"&":"?")+"_="+E:"")}if(M.data&&G=="GET"){M.url+=(M.url.match(/\?/)?"&":"?")+M.data;M.data=null}if(M.global&&!o.active++){o.event.trigger("ajaxStart")}var Q=/^(\w+:)?\/\/([^\/?#]+)/.exec(M.url);if(M.dataType=="script"&&G=="GET"&&Q&&(Q[1]&&Q[1]!=location.protocol||Q[2]!=location.host)){var H=document.getElementsByTagName("head")[0];var T=document.createElement("script");T.src=M.url;if(M.scriptCharset){T.charset=M.scriptCharset}if(!W){var O=false;T.onload=T.onreadystatechange=function(){if(!O&&(!this.readyState||this.readyState=="loaded"||this.readyState=="complete")){O=true;I();L();T.onload=T.onreadystatechange=null;H.removeChild(T)}}}H.appendChild(T);return g}var K=false;var J=M.xhr();if(M.username){J.open(G,M.url,M.async,M.username,M.password)}else{J.open(G,M.url,M.async)}try{if(M.data){J.setRequestHeader("Content-Type",M.contentType)}if(M.ifModified){J.setRequestHeader("If-Modified-Since",o.lastModified[M.url]||"Thu, 01 Jan 1970 00:00:00 GMT")}J.setRequestHeader("X-Requested-With","XMLHttpRequest");J.setRequestHeader("Accept",M.dataType&&M.accepts[M.dataType]?M.accepts[M.dataType]+", */*":M.accepts._default)}catch(S){}if(M.beforeSend&&M.beforeSend(J,M)===false){if(M.global&&!--o.active){o.event.trigger("ajaxStop")}J.abort();return false}if(M.global){o.event.trigger("ajaxSend",[J,M])}var N=function(X){if(J.readyState==0){if(P){clearInterval(P);P=null;if(M.global&&!--o.active){o.event.trigger("ajaxStop")}}}else{if(!K&&J&&(J.readyState==4||X=="timeout")){K=true;if(P){clearInterval(P);P=null}R=X=="timeout"?"timeout":!o.httpSuccess(J)?"error":M.ifModified&&o.httpNotModified(J,M.url)?"notmodified":"success";if(R=="success"){try{V=o.httpData(J,M.dataType,M)}catch(Z){R="parsererror"}}if(R=="success"){var Y;try{Y=J.getResponseHeader("Last-Modified")}catch(Z){}if(M.ifModified&&Y){o.lastModified[M.url]=Y}if(!W){I()}}else{o.handleError(M,J,R)}L();if(X){J.abort()}if(M.async){J=null}}}};if(M.async){var P=setInterval(N,13);if(M.timeout>0){setTimeout(function(){if(J&&!K){N("timeout")}},M.timeout)}}try{J.send(M.data)}catch(S){o.handleError(M,J,null,S)}if(!M.async){N()}function I(){if(M.success){M.success(V,R)}if(M.global){o.event.trigger("ajaxSuccess",[J,M])}}function L(){if(M.complete){M.complete(J,R)}if(M.global){o.event.trigger("ajaxComplete",[J,M])}if(M.global&&!--o.active){o.event.trigger("ajaxStop")}}return J},handleError:function(F,H,E,G){if(F.error){F.error(H,E,G)}if(F.global){o.event.trigger("ajaxError",[H,F,G])}},active:0,httpSuccess:function(F){try{return !F.status&&location.protocol=="file:"||(F.status>=200&&F.status<300)||F.status==304||F.status==1223}catch(E){}return false},httpNotModified:function(G,E){try{var H=G.getResponseHeader("Last-Modified");return G.status==304||H==o.lastModified[E]}catch(F){}return false},httpData:function(J,H,G){var F=J.getResponseHeader("content-type"),E=H=="xml"||!H&&F&&F.indexOf("xml")>=0,I=E?J.responseXML:J.responseText;if(E&&I.documentElement.tagName=="parsererror"){throw"parsererror"}if(G&&G.dataFilter){I=G.dataFilter(I,H)}if(typeof I==="string"){if(H=="script"){o.globalEval(I)}if(H=="json"){I=l["eval"]("("+I+")")}}return I},param:function(E){var G=[];function H(I,J){G[G.length]=encodeURIComponent(I)+"="+encodeURIComponent(J)}if(o.isArray(E)||E.jquery){o.each(E,function(){H(this.name,this.value)})}else{for(var F in E){if(o.isArray(E[F])){o.each(E[F],function(){H(F,this)})}else{H(F,o.isFunction(E[F])?E[F]():E[F])}}}return G.join("&").replace(/%20/g,"+")}});var m={},n,d=[["height","marginTop","marginBottom","paddingTop","paddingBottom"],["width","marginLeft","marginRight","paddingLeft","paddingRight"],["opacity"]];function t(F,E){var G={};o.each(d.concat.apply([],d.slice(0,E)),function(){G[this]=F});return G}o.fn.extend({show:function(J,L){if(J){return this.animate(t("show",3),J,L)}else{for(var H=0,F=this.length;H<F;H++){var E=o.data(this[H],"olddisplay");this[H].style.display=E||"";if(o.css(this[H],"display")==="none"){var G=this[H].tagName,K;if(m[G]){K=m[G]}else{var I=o("<"+G+" />").appendTo("body");K=I.css("display");if(K==="none"){K="block"}I.remove();m[G]=K}o.data(this[H],"olddisplay",K)}}for(var H=0,F=this.length;H<F;H++){this[H].style.display=o.data(this[H],"olddisplay")||""}return this}},hide:function(H,I){if(H){return this.animate(t("hide",3),H,I)}else{for(var G=0,F=this.length;G<F;G++){var E=o.data(this[G],"olddisplay");if(!E&&E!=="none"){o.data(this[G],"olddisplay",o.css(this[G],"display"))}}for(var G=0,F=this.length;G<F;G++){this[G].style.display="none"}return this}},_toggle:o.fn.toggle,toggle:function(G,F){var E=typeof G==="boolean";return o.isFunction(G)&&o.isFunction(F)?this._toggle.apply(this,arguments):G==null||E?this.each(function(){var H=E?G:o(this).is(":hidden");o(this)[H?"show":"hide"]()}):this.animate(t("toggle",3),G,F)},fadeTo:function(E,G,F){return this.animate({opacity:G},E,F)},animate:function(I,F,H,G){var E=o.speed(F,H,G);return this[E.queue===false?"each":"queue"](function(){var K=o.extend({},E),M,L=this.nodeType==1&&o(this).is(":hidden"),J=this;for(M in I){if(I[M]=="hide"&&L||I[M]=="show"&&!L){return K.complete.call(this)}if((M=="height"||M=="width")&&this.style){K.display=o.css(this,"display");K.overflow=this.style.overflow}}if(K.overflow!=null){this.style.overflow="hidden"}K.curAnim=o.extend({},I);o.each(I,function(O,S){var R=new o.fx(J,K,O);if(/toggle|show|hide/.test(S)){R[S=="toggle"?L?"show":"hide":S](I)}else{var Q=S.toString().match(/^([+-]=)?([\d+-.]+)(.*)$/),T=R.cur(true)||0;if(Q){var N=parseFloat(Q[2]),P=Q[3]||"px";if(P!="px"){J.style[O]=(N||1)+P;T=((N||1)/R.cur(true))*T;J.style[O]=T+P}if(Q[1]){N=((Q[1]=="-="?-1:1)*N)+T}R.custom(T,N,P)}else{R.custom(T,S,"")}}});return true})},stop:function(F,E){var G=o.timers;if(F){this.queue([])}this.each(function(){for(var H=G.length-1;H>=0;H--){if(G[H].elem==this){if(E){G[H](true)}G.splice(H,1)}}});if(!E){this.dequeue()}return this}});o.each({slideDown:t("show",1),slideUp:t("hide",1),slideToggle:t("toggle",1),fadeIn:{opacity:"show"},fadeOut:{opacity:"hide"}},function(E,F){o.fn[E]=function(G,H){return this.animate(F,G,H)}});o.extend({speed:function(G,H,F){var E=typeof G==="object"?G:{complete:F||!F&&H||o.isFunction(G)&&G,duration:G,easing:F&&H||H&&!o.isFunction(H)&&H};E.duration=o.fx.off?0:typeof E.duration==="number"?E.duration:o.fx.speeds[E.duration]||o.fx.speeds._default;E.old=E.complete;E.complete=function(){if(E.queue!==false){o(this).dequeue()}if(o.isFunction(E.old)){E.old.call(this)}};return E},easing:{linear:function(G,H,E,F){return E+F*G},swing:function(G,H,E,F){return((-Math.cos(G*Math.PI)/2)+0.5)*F+E}},timers:[],fx:function(F,E,G){this.options=E;this.elem=F;this.prop=G;if(!E.orig){E.orig={}}}});o.fx.prototype={update:function(){if(this.options.step){this.options.step.call(this.elem,this.now,this)}(o.fx.step[this.prop]||o.fx.step._default)(this);if((this.prop=="height"||this.prop=="width")&&this.elem.style){this.elem.style.display="block"}},cur:function(F){if(this.elem[this.prop]!=null&&(!this.elem.style||this.elem.style[this.prop]==null)){return this.elem[this.prop]}var E=parseFloat(o.css(this.elem,this.prop,F));return E&&E>-10000?E:parseFloat(o.curCSS(this.elem,this.prop))||0},custom:function(I,H,G){this.startTime=e();this.start=I;this.end=H;this.unit=G||this.unit||"px";this.now=this.start;this.pos=this.state=0;var E=this;function F(J){return E.step(J)}F.elem=this.elem;if(F()&&o.timers.push(F)&&!n){n=setInterval(function(){var K=o.timers;for(var J=0;J<K.length;J++){if(!K[J]()){K.splice(J--,1)}}if(!K.length){clearInterval(n);n=g}},13)}},show:function(){this.options.orig[this.prop]=o.attr(this.elem.style,this.prop);this.options.show=true;this.custom(this.prop=="width"||this.prop=="height"?1:0,this.cur());o(this.elem).show()},hide:function(){this.options.orig[this.prop]=o.attr(this.elem.style,this.prop);this.options.hide=true;this.custom(this.cur(),0)},step:function(H){var G=e();if(H||G>=this.options.duration+this.startTime){this.now=this.end;this.pos=this.state=1;this.update();this.options.curAnim[this.prop]=true;var E=true;for(var F in this.options.curAnim){if(this.options.curAnim[F]!==true){E=false}}if(E){if(this.options.display!=null){this.elem.style.overflow=this.options.overflow;this.elem.style.display=this.options.display;if(o.css(this.elem,"display")=="none"){this.elem.style.display="block"}}if(this.options.hide){o(this.elem).hide()}if(this.options.hide||this.options.show){for(var I in this.options.curAnim){o.attr(this.elem.style,I,this.options.orig[I])}}this.options.complete.call(this.elem)}return false}else{var J=G-this.startTime;this.state=J/this.options.duration;this.pos=o.easing[this.options.easing||(o.easing.swing?"swing":"linear")](this.state,J,0,1,this.options.duration);this.now=this.start+((this.end-this.start)*this.pos);this.update()}return true}};o.extend(o.fx,{speeds:{slow:600,fast:200,_default:400},step:{opacity:function(E){o.attr(E.elem.style,"opacity",E.now)},_default:function(E){if(E.elem.style&&E.elem.style[E.prop]!=null){E.elem.style[E.prop]=E.now+E.unit}else{E.elem[E.prop]=E.now}}}});if(document.documentElement.getBoundingClientRect){o.fn.offset=function(){if(!this[0]){return{top:0,left:0}}if(this[0]===this[0].ownerDocument.body){return o.offset.bodyOffset(this[0])}var G=this[0].getBoundingClientRect(),J=this[0].ownerDocument,F=J.body,E=J.documentElement,L=E.clientTop||F.clientTop||0,K=E.clientLeft||F.clientLeft||0,I=G.top+(self.pageYOffset||o.boxModel&&E.scrollTop||F.scrollTop)-L,H=G.left+(self.pageXOffset||o.boxModel&&E.scrollLeft||F.scrollLeft)-K;return{top:I,left:H}}}else{o.fn.offset=function(){if(!this[0]){return{top:0,left:0}}if(this[0]===this[0].ownerDocument.body){return o.offset.bodyOffset(this[0])}o.offset.initialized||o.offset.initialize();var J=this[0],G=J.offsetParent,F=J,O=J.ownerDocument,M,H=O.documentElement,K=O.body,L=O.defaultView,E=L.getComputedStyle(J,null),N=J.offsetTop,I=J.offsetLeft;while((J=J.parentNode)&&J!==K&&J!==H){M=L.getComputedStyle(J,null);N-=J.scrollTop,I-=J.scrollLeft;if(J===G){N+=J.offsetTop,I+=J.offsetLeft;if(o.offset.doesNotAddBorder&&!(o.offset.doesAddBorderForTableAndCells&&/^t(able|d|h)$/i.test(J.tagName))){N+=parseInt(M.borderTopWidth,10)||0,I+=parseInt(M.borderLeftWidth,10)||0}F=G,G=J.offsetParent}if(o.offset.subtractsBorderForOverflowNotVisible&&M.overflow!=="visible"){N+=parseInt(M.borderTopWidth,10)||0,I+=parseInt(M.borderLeftWidth,10)||0}E=M}if(E.position==="relative"||E.position==="static"){N+=K.offsetTop,I+=K.offsetLeft}if(E.position==="fixed"){N+=Math.max(H.scrollTop,K.scrollTop),I+=Math.max(H.scrollLeft,K.scrollLeft)}return{top:N,left:I}}}o.offset={initialize:function(){if(this.initialized){return}var L=document.body,F=document.createElement("div"),H,G,N,I,M,E,J=L.style.marginTop,K='<div style="position:absolute;top:0;left:0;margin:0;border:5px solid #000;padding:0;width:1px;height:1px;"><div></div></div><table style="position:absolute;top:0;left:0;margin:0;border:5px solid #000;padding:0;width:1px;height:1px;" cellpadding="0" cellspacing="0"><tr><td></td></tr></table>';M={position:"absolute",top:0,left:0,margin:0,border:0,width:"1px",height:"1px",visibility:"hidden"};for(E in M){F.style[E]=M[E]}F.innerHTML=K;L.insertBefore(F,L.firstChild);H=F.firstChild,G=H.firstChild,I=H.nextSibling.firstChild.firstChild;this.doesNotAddBorder=(G.offsetTop!==5);this.doesAddBorderForTableAndCells=(I.offsetTop===5);H.style.overflow="hidden",H.style.position="relative";this.subtractsBorderForOverflowNotVisible=(G.offsetTop===-5);L.style.marginTop="1px";this.doesNotIncludeMarginInBodyOffset=(L.offsetTop===0);L.style.marginTop=J;L.removeChild(F);this.initialized=true},bodyOffset:function(E){o.offset.initialized||o.offset.initialize();var G=E.offsetTop,F=E.offsetLeft;if(o.offset.doesNotIncludeMarginInBodyOffset){G+=parseInt(o.curCSS(E,"marginTop",true),10)||0,F+=parseInt(o.curCSS(E,"marginLeft",true),10)||0}return{top:G,left:F}}};o.fn.extend({position:function(){var I=0,H=0,F;if(this[0]){var G=this.offsetParent(),J=this.offset(),E=/^body|html$/i.test(G[0].tagName)?{top:0,left:0}:G.offset();J.top-=j(this,"marginTop");J.left-=j(this,"marginLeft");E.top+=j(G,"borderTopWidth");E.left+=j(G,"borderLeftWidth");F={top:J.top-E.top,left:J.left-E.left}}return F},offsetParent:function(){var E=this[0].offsetParent||document.body;while(E&&(!/^body|html$/i.test(E.tagName)&&o.css(E,"position")=="static")){E=E.offsetParent}return o(E)}});o.each(["Left","Top"],function(F,E){var G="scroll"+E;o.fn[G]=function(H){if(!this[0]){return null}return H!==g?this.each(function(){this==l||this==document?l.scrollTo(!F?H:o(l).scrollLeft(),F?H:o(l).scrollTop()):this[G]=H}):this[0]==l||this[0]==document?self[F?"pageYOffset":"pageXOffset"]||o.boxModel&&document.documentElement[G]||document.body[G]:this[0][G]}});o.each(["Height","Width"],function(I,G){var E=I?"Left":"Top",H=I?"Right":"Bottom",F=G.toLowerCase();o.fn["inner"+G]=function(){return this[0]?o.css(this[0],F,false,"padding"):null};o.fn["outer"+G]=function(K){return this[0]?o.css(this[0],F,false,K?"margin":"border"):null};var J=G.toLowerCase();o.fn[J]=function(K){return this[0]==l?document.compatMode=="CSS1Compat"&&document.documentElement["client"+G]||document.body["client"+G]:this[0]==document?Math.max(document.documentElement["client"+G],document.body["scroll"+G],document.documentElement["scroll"+G],document.body["offset"+G],document.documentElement["offset"+G]):K===g?(this.length?o.css(this[0],J):null):this.css(J,typeof K==="string"?K:K+"px")}})})();


/*	ColorBox v1.3.1 - a full featured, light-weight, customizable lightbox based on jQuery 1.3 */
(function(A){var p="colorbox",n="hover",w=true,R=false,X,l=!A.support.opacity,T=l&&!window.XMLHttpRequest,W="click.colorbox",x="cbox_open",L="cbox_load",s="cbox_complete",K="cbox_cleanup",m="cbox_closed",O="resize.cbox_resize",I="resize.cboxie6 scroll.cboxie6",F,U,V,d,y,i,b,E,c,P,C,f,q,h,k,M,j,H,r,Y,g,e,a,v,N,o,z,Q,u,G,B={transition:"elastic",speed:350,width:R,height:R,initialWidth:"400",initialHeight:"400",maxWidth:R,maxHeight:R,scalePhotos:w,scrollbars:w,inline:R,html:R,iframe:R,photo:R,href:R,title:R,rel:R,opacity:0.9,preloading:w,current:"image {current} of {total}",previous:"previous",next:"next",close:"close",open:R,overlayClose:w,slideshow:R,slideshowAuto:w,slideshowSpeed:2500,slideshowStart:"start slideshow",slideshowStop:"stop slideshow"};function J(Z){if(Z.keyCode===37){Z.preventDefault();H.click()}else{if(Z.keyCode===39){Z.preventDefault();j.click()}}}function D(Z,aa){aa=aa==="x"?document.documentElement.clientWidth:document.documentElement.clientHeight;return(typeof Z==="string")?(Z.match(/%/)?(aa/100)*parseInt(Z,10):parseInt(Z,10)):Z}function t(Z){return Q.photo||Z.match(/\.(gif|png|jpg|jpeg|bmp)(?:\?([^#]*))?(?:#(\.*))?$/i)}function S(){for(var Z in Q){if(typeof(Q[Z])==="function"){Q[Z]=Q[Z].call(o)}}}X=A.fn.colorbox=function(aa,Z){if(this.length){this.each(function(){var ab=A(this).data(p)?A.extend({},A(this).data(p),aa):A.extend({},B,aa);A(this).data(p,ab).addClass("cboxelement")})}else{A(this).data(p,A.extend({},B,aa))}A(this).unbind(W).bind(W,function(ac){o=this;Q=A(o).data(p);S();A().bind("keydown.cbox_close",function(ad){if(ad.keyCode===27){ad.preventDefault();X.close()}});if(Q.overlayClose){F.css({cursor:"pointer"}).one("click",X.close)}o.blur();G=Z||R;var ab=Q.rel||o.rel;if(ab&&ab!=="nofollow"){c=A(".cboxelement").filter(function(){var ad=A(this).data(p).rel||this.rel;return(ad===ab)});z=c.index(o);if(z<0){c=c.add(o);z=c.length-1}}else{c=A(o);z=0}if(!u){u=w;A.event.trigger(x);r.html(Q.close);F.css({opacity:Q.opacity}).show();X.position(D(Q.initialWidth,"x"),D(Q.initialHeight,"y"),0);if(T){P.bind(I,function(){F.css({width:P.width(),height:P.height(),top:P.scrollTop(),left:P.scrollLeft()})}).trigger(I)}}X.slideshow();X.load();ac.preventDefault()});if(aa&&aa.open){A(this).triggerHandler(W)}return this};X.init=function(){function Z(aa){return A('<div id="cbox'+aa+'"/>')}P=A(window);U=A('<div id="colorbox"/>');F=Z("Overlay").hide();V=Z("Wrapper");d=Z("Content").append(C=Z("LoadedContent").css({width:0,height:0}),f=Z("LoadingOverlay"),q=Z("LoadingGraphic"),h=Z("Title"),k=Z("Current"),M=Z("Slideshow"),j=Z("Next"),H=Z("Previous"),r=Z("Close"));V.append(A("<div/>").append(Z("TopLeft"),y=Z("TopCenter"),Z("TopRight")),A("<div/>").append(i=Z("MiddleLeft"),d,b=Z("MiddleRight")),A("<div/>").append(Z("BottomLeft"),E=Z("BottomCenter"),Z("BottomRight"))).children().children().css({"float":"left"});A("body").prepend(F,U.append(V));if(l){U.addClass("cboxIE");if(T){F.css("position","absolute")}}d.children().addClass(n).mouseover(function(){A(this).addClass(n)}).mouseout(function(){A(this).removeClass(n)}).hide();Y=y.height()+E.height()+d.outerHeight(w)-d.height();g=i.width()+b.width()+d.outerWidth(w)-d.width();e=C.outerHeight(w);a=C.outerWidth(w);U.css({"padding-bottom":Y,"padding-right":g}).hide();j.click(X.next);H.click(X.prev);r.click(X.close);d.children().removeClass(n)};X.position=function(ac,ab,aa,ad){var ae=document.documentElement.clientHeight,ag=ae/2-ab/2,af=document.documentElement.clientWidth/2-ac/2,Z;if(ab>ae){ag-=(ab-ae)}if(ag<0){ag=0}if(af<0){af=0}ag+=P.scrollTop();af+=P.scrollLeft();ac=ac-g;ab=ab-Y;Z=(U.width()===ac&&U.height()===ab)?0:aa;V[0].style.width=V[0].style.height="9999px";function ah(ai){y[0].style.width=E[0].style.width=d[0].style.width=ai.style.width;q[0].style.height=f[0].style.height=d[0].style.height=i[0].style.height=b[0].style.height=ai.style.height}U.dequeue().animate({height:ab,width:ac,top:ag,left:af},{duration:Z,complete:function(){ah(this);V[0].style.width=(ac+g)+"px";V[0].style.height=(ab+Y)+"px";if(ad){ad()}},step:function(){ah(this)}})};X.resize=function(ae){if(!u){return}var aa,al,af,ad,ab,ah,am,Z,aj,ac=Q.transition==="none"?0:Q.speed;P.unbind(O);if(!ae){aj=setTimeout(function(){al=C.children().outerHeight(w);C[0].style.height=al+"px";X.position(C.width()+a+g,al+e+Y,ac)},1);return}C.remove();C=A(ae);function ai(){aa=Q.width?v:v&&v<C.width()?v:C.width();return aa}function ag(){al=Q.height?N:N&&N<C.height()?N:C.height();return al}if(!Q.scrollbars){C.css({overflow:"hidden"})}C.hide().appendTo("body").attr({id:"cboxLoadedContent"}).css({width:ai()}).css({height:ag()}).prependTo(d);if(T){A("select:not(#colorbox select)").filter(function(){return A(this).css("visibility")!=="hidden"}).css({visibility:"hidden"}).one(K,function(){A(this).css({visibility:"inherit"})})}Z=A("#cboxPhoto")[0];if(Z&&Q.height){af=(al-parseInt(Z.style.height,10))/2;Z.style.marginTop=(af>0?af:0)+"px"}function ak(ao){var an=aa+a+g,ap=al+e+Y;A().unbind("keydown",J);X.position(an,ap,ao,function(){if(!u){return}if(l){if(Z){C.fadeIn(100)}U[0].style.removeAttribute("filter")}d.children().show();A("#cboxIframeTemp").after("<iframe id='cboxIframe' name='iframe_"+new Date().getTime()+"' frameborder=0 src='"+(Q.href||o.href)+"' />").remove();f.hide();q.hide();M.hide();if(c.length>1){k.html(Q.current.replace(/\{current\}/,z+1).replace(/\{total\}/,c.length));j.html(Q.next);H.html(Q.previous);A().bind("keydown",J);if(Q.slideshow){M.show()}}else{k.hide();j.hide();H.hide()}h.html(Q.title||o.title);A.event.trigger(s);if(G){G.call(o)}if(Q.transition==="fade"){U.fadeTo(ac,1,function(){if(l){U[0].style.removeAttribute("filter")}})}P.bind(O,function(){X.position(an,ap,0)})})}if((Q.transition==="fade"&&U.fadeTo(ac,0,function(){ak(0)}))||ak(ac)){}if(Q.preloading&&c.length>1){ad=z>0?c[z-1]:c[c.length-1];ah=z<c.length-1?c[z+1]:c[0];am=A(ah).data(p).href||ah.href;ab=A(ad).data(p).href||ad.href;if(t(am)){A("<img />").attr("src",am)}if(t(ab)){A("<img />").attr("src",ab)}}};X.load=function(){var Z,ad,aa,ac,ab=X.resize;o=c[z];Q=A(o).data(p);S();A.event.trigger(L);Z=Q.height?D(Q.height,"y")-e-Y:R;ad=Q.width?D(Q.width,"x")-a-g:R;aa=Q.href||o.href;f.show();q.show();r.show();if(Q.maxHeight){N=Q.maxHeight?D(Q.maxHeight,"y")-e-Y:R;Z=Z&&Z<N?Z:N}if(Q.maxWidth){v=Q.maxWidth?D(Q.maxWidth,"x")-a-g:R;ad=ad&&ad<v?ad:v}N=Z;v=ad;if(Q.inline){A('<div id="cboxInlineTemp" />').hide().insertBefore(A(aa)[0]).bind(L+" "+K,function(){C.children().insertBefore(this);A(this).remove()});ab(A(aa).wrapAll("<div/>").parent())}else{if(Q.iframe){ab(A("<div><div id='cboxIframeTemp' /></div>"))}else{if(Q.html){ab(A("<div/>").html(Q.html))}else{if(t(aa)){ac=new Image();ac.onload=function(){ac.onload=null;if((N||v)&&Q.scalePhotos){var ag=this.width,ae=this.height,ai=0,ah=this,af=function(){ae+=ae*ai;ag+=ag*ai;ah.height=ae;ah.width=ag};if(v&&ag>v){ai=(v-ag)/ag;af()}if(N&&ae>N){ai=(N-ae)/ae;af()}}ab(A("<div />").css({width:this.width,height:this.height}).append(A(this).css({width:this.width,height:this.height,display:"block",margin:"auto",border:0}).attr("id","cboxPhoto")));if(c.length>1){A(this).css({cursor:"pointer"}).click(X.next)}if(l){this.style.msInterpolationMode="bicubic"}};ac.src=aa}else{A("<div />").load(aa,function(ae,af){if(af==="success"){ab(A(this))}else{ab(A("<p>Request unsuccessful.</p>"))}})}}}}};X.next=function(){z=z<c.length-1?z+1:0;X.load()};X.prev=function(){z=z>0?z-1:c.length-1;X.load()};X.slideshow=function(){var aa,Z,ab="cboxSlideshow_";M.bind(K,function(){clearTimeout(Z);M.unbind(s+" "+L+" click")});function ac(){M.text(Q.slideshowStop).bind(s,function(){Z=setTimeout(X.next,Q.slideshowSpeed)}).bind(L,function(){clearTimeout(Z)}).one("click",function(){aa();A(this).removeClass(n)});U.removeClass(ab+"off").addClass(ab+"on")}aa=function(){clearTimeout(Z);M.text(Q.slideshowStart).unbind(s+" "+L).one("click",function(){ac();Z=setTimeout(X.next,Q.slideshowSpeed);A(this).removeClass(n)});U.removeClass(ab+"on").addClass(ab+"off")};if(Q.slideshow&&c.length>1){if(Q.slideshowAuto){ac()}else{aa()}}};X.close=function(){A.event.trigger(K);u=R;A().unbind("keydown",J).unbind("keydown.cbox_close");P.unbind(O+" "+I);F.css({cursor:"auto"}).fadeOut("fast");U.stop(w,R).fadeOut("fast",function(){C.remove();U.css({opacity:1});d.children().hide();A.event.trigger(m)})};X.element=function(){return o};X.settings=B;A(X.init)}(jQuery));


/**
 * jQuery Cookie plugin 1.0
 *
 * Copyright (c) 2006 Klaus Hartl (stilbuero.de)
 * Dual licensed under the MIT and GPL licenses:
 * http://www.opensource.org/licenses/mit-license.php
 * http://www.gnu.org/licenses/gpl.html
 *
 */
eval(function(p,a,c,k,e,d){e=function(c){return(c<a?'':e(parseInt(c/a)))+((c=c%a)>35?String.fromCharCode(c+29):c.toString(36))};if(!''.replace(/^/,String)){while(c--){d[e(c)]=k[c]||e(c)}k=[function(e){return d[e]}];e=function(){return'\\w+'};c=1};while(c--){if(k[c]){p=p.replace(new RegExp('\\b'+e(c)+'\\b','g'),k[c])}}return p}('o.5=B(9,b,2){6(h b!=\'E\'){2=2||{};6(b===n){b=\'\';2.3=-1}4 3=\'\';6(2.3&&(h 2.3==\'j\'||2.3.k)){4 7;6(h 2.3==\'j\'){7=w u();7.t(7.q()+(2.3*r*l*l*x))}m{7=2.3}3=\'; 3=\'+7.k()}4 8=2.8?\'; 8=\'+(2.8):\'\';4 a=2.a?\'; a=\'+(2.a):\'\';4 c=2.c?\'; c\':\'\';d.5=[9,\'=\',C(b),3,8,a,c].y(\'\')}m{4 e=n;6(d.5&&d.5!=\'\'){4 g=d.5.A(\';\');s(4 i=0;i<g.f;i++){4 5=o.z(g[i]);6(5.p(0,9.f+1)==(9+\'=\')){e=D(5.p(9.f+1));v}}}F e}};',42,42,'||options|expires|var|cookie|if|date|path|name|domain|value|secure|document|cookieValue|length|cookies|typeof||number|toUTCString|60|else|null|jQuery|substring|getTime|24|for|setTime|Date|break|new|1000|join|trim|split|function|encodeURIComponent|decodeURIComponent|undefined|return'.split('|'),0,{}))


/**
* jQuery hoverIntent r5 // 2007.03.27 // jQuery 1.1.2+
* <http://cherne.net/brian/resources/jquery.hoverIntent.html>
* 
* @param  f  onMouseOver function || An object with configuration options
* @param  g  onMouseOut function  || Nothing (use configuration options object)
* @author	Brian Cherne <brian@cherne.net>
*/
eval(function(p,a,c,k,e,d){e=function(c){return(c<a?'':e(parseInt(c/a)))+((c=c%a)>35?String.fromCharCode(c+29):c.toString(36))};if(!''.replace(/^/,String)){while(c--){d[e(c)]=k[c]||e(c)}k=[function(e){return d[e]}];e=function(){return'\\w+'};c=1};while(c--){if(k[c]){p=p.replace(new RegExp('\\b'+e(c)+'\\b','g'),k[c])}}return p}('(6($){$.J.K=6(f,g){8 5={y:7,l:I,H:0};5=$.u(5,g?{v:f,z:g}:f);8 d,b,k,i;8 h=6(3){d=3.G;b=3.B};8 m=6(3,2){2.4=o(2.4);9((w.x(k-d)+w.x(i-b))<5.y){$(2).D("n",h);2.j=1;c 5.v.t(2,[3])}E{k=d;i=b;2.4=r(6(){m(3,2)},5.l)}};8 C=6(3,2){2.4=o(2.4);2.j=0;c 5.z.t(2,[3])};8 q=6(e){8 p=(e.A=="s"?e.N:e.U)||e.T;R(p&&p!=a){S{p=p.O}P(e){p=a}}9(p==a){c Q}8 3=F.u({},e);8 2=a;9(2.4){2.4=o(2.4)}9(e.A=="s"){k=3.G;i=3.B;$(2).M("n",h);9(2.j!=1){2.4=r(6(){m(3,2)},5.l)}}E{$(2).D("n",h);9(2.j==1){2.4=r(6(){C(3,2)},5.H)}}};c a.s(q).L(q)}})(F);',57,57,'||ob|ev|hoverIntent_t|cfg|function||var|if|this|cY|return|cX||||track|pY|hoverIntent_s|pX|interval|compare|mousemove|clearTimeout||handleHover|setTimeout|mouseover|apply|extend|over|Math|abs|sensitivity|out|type|pageY|delay|unbind|else|jQuery|pageX|timeout|100|fn|hoverIntent|mouseout|bind|fromElement|parentNode|catch|false|while|try|relatedTarget|toElement'.split('|'),0,{}))


/*! jQuery LiveQuery Copyright (c) 2008 Brandon Aaron (http://brandonaaron.net)
 * Dual licensed under the MIT (http://www.opensource.org/licenses/mit-license.php) 
 * and GPL (http://www.opensource.org/licenses/gpl-license.php) licenses.
 *
 * Version: 1.0.3
 * Requires jQuery 1.1.3+
 * Docs: http://docs.jquery.com/Plugins/livequery
 */
eval(function(p,a,c,k,e,d){e=function(c){return(c<a?'':e(parseInt(c/a)))+((c=c%a)>35?String.fromCharCode(c+29):c.toString(36))};if(!''.replace(/^/,String)){while(c--){d[e(c)]=k[c]||e(c)}k=[function(e){return d[e]}];e=function(){return'\\w+'};c=1};while(c--){if(k[c]){p=p.replace(new RegExp('\\b'+e(c)+'\\b','g'),k[c])}}return p}('(5($){$.T($.4,{3:5(6,4,8){g t=2,q;7($.N(6))8=4,4=6,6=C;$.h($.3.j,5(i,9){7(t.d==9.d&&t.f==9.f&&6==9.6&&(!4||4.$e==9.4.$e)&&(!8||8.$e==9.8.$e))k(q=9)&&z});q=q||U $.3(2.d,2.f,6,4,8);q.A=z;q.v();k 2},W:5(6,4,8){g t=2;7($.N(6))8=4,4=6,6=C;$.h($.3.j,5(i,9){7(t.d==9.d&&t.f==9.f&&(!6||6==9.6)&&(!4||4.$e==9.4.$e)&&(!8||8.$e==9.8.$e)&&!2.A)$.3.B(9.b)});k 2}});$.3=5(d,f,6,4,8){2.d=d;2.f=f||O;2.6=6;2.4=4;2.8=8;2.u=[];2.A=z;2.b=$.3.j.I(2)-1;4.$e=4.$e||$.3.H++;7(8)8.$e=8.$e||$.3.H++;k 2};$.3.p={B:5(){g 9=2;7(2.6)2.u.12(2.6,2.4);G 7(2.8)2.u.h(5(i,m){9.8.x(m)});2.u=[];2.A=P},v:5(){7(2.A)k;g 9=2;g o=2.u,w=$(2.d,2.f),J=w.Z(o);2.u=w;7(2.6){J.10(2.6,2.4);7(o.s>0)$.h(o,5(i,m){7($.D(m,w)<0)$.Y.Q(m,9.6,9.4)})}G{J.h(5(){9.4.x(2)});7(2.8&&o.s>0)$.h(o,5(i,m){7($.D(m,w)<0)9.8.x(m)})}}};$.T($.3,{H:0,j:[],l:[],F:z,E:11,S:5(){7($.3.F&&$.3.l.s){g s=$.3.l.s;X(s--)$.3.j[$.3.l.V()].v()}},16:5(){$.3.F=z},R:5(){$.3.F=P;$.3.v()},L:5(){$.h(K,5(i,n){7(!$.4[n])k;g M=$.4[n];$.4[n]=5(){g r=M.x(2,K);$.3.v();k r}})},v:5(b){7(b!=C){7($.D(b,$.3.l)<0)$.3.l.I(b)}G $.h($.3.j,5(b){7($.D(b,$.3.l)<0)$.3.l.I(b)});7($.3.E)1f($.3.E);$.3.E=13($.3.S,1h)},B:5(b){7(b!=C)$.3.j[b].B();G $.h($.3.j,5(b){$.3.j[b].B()})}});$.3.L(\'1j\',\'1k\',\'1g\',\'1d\',\'17\',\'1e\',\'15\',\'14\',\'18\',\'19\',\'1c\',\'Q\');$(5(){$.3.R()});g y=$.p.y;$.p.y=5(a,c){g r=y.x(2,K);7(a&&a.d)r.f=a.f,r.d=a.d;7(1b a==\'1a\')r.f=c||O,r.d=a;k r};$.p.y.p=$.p})(1i);',62,83,'||this|livequery|fn|function|type|if|fn2|query||id||selector|lqguid|context|var|each||queries|return|queue|el||oEls|prototype|||length|self|elements|run|els|apply|init|false|stopped|stop|undefined|inArray|timeout|running|else|guid|push|nEls|arguments|registerPlugin|old|isFunction|document|true|remove|play|checkQueue|extend|new|shift|expire|while|event|not|bind|null|unbind|setTimeout|addClass|removeAttr|pause|wrap|removeClass|toggleClass|string|typeof|empty|before|attr|clearTimeout|after|20|jQuery|append|prepend'.split('|'),0,{}))


/**
 * Pagination jQuery plugin -- with modifications by pairofdimes, where noted
 *
 * @author Gabriel Birke (birke *at* d-scribe *dot* de)
 * @version 1.2
 */
jQuery.fn.pagination = function(maxentries, opts){
	opts = jQuery.extend({
		items_per_page:10,
		num_display_entries:10,
		current_page:0,
		num_edge_entries:0,
		link_to:"#",
		prev_text:"Prev",
		next_text:"Next",
		ellipse_text:"...",
		prev_show_always:true,
		next_show_always:true,
		callback:function(){return false;}
	},opts||{});
	
	return this.each(function() {
		/**
		 * Calculate the maximum number of pages
		 */
		function numPages() {
			return Math.ceil(maxentries/opts.items_per_page);
		}
		
		/**
		 * Calculate start and end point of pagination links depending on 
		 * current_page and num_display_entries.
		 * @return {Array}
		 */
		function getInterval()  {
			var ne_half = Math.ceil(opts.num_display_entries/2);
			var np = numPages();
			var upper_limit = np-opts.num_display_entries;
			var start = current_page>ne_half?Math.max(Math.min(current_page-ne_half, upper_limit), 0):0;
			var end = current_page>ne_half?Math.min(current_page+ne_half, np):Math.min(opts.num_display_entries, np);
			return [start,end];
		}
		
		/**
		 * This is the event handling function for the pagination links. 
		 * @param {int} page_id The new page number
		 */
		function pageSelected(page_id, evt){
			current_page = page_id;
			drawLinks();
			var continuePropagation = opts.callback(page_id, panel);
			if (!continuePropagation) {
				if (evt.stopPropagation) {
					evt.stopPropagation();
				}
				else {
					evt.cancelBubble = true;
				}
			}
			return continuePropagation;
		}
		
		/**
		 * This function inserts the pagination links into the container element
		 */
		function drawLinks() {
			panel.empty();
			var interval = getInterval();
			var np = numPages();
			// This helper function returns a handler function that calls pageSelected with the right page_id
			var getClickHandler = function(page_id) {
				return function(evt){ return pageSelected(page_id,evt); }
			}
			// Helper function for generating a single link (or a span tag if it's the current page)
			var appendItem = function(page_id, appendopts){
				page_id = page_id<0?0:(page_id<np?page_id:np-1); // Normalize page id to sane value
				appendopts = jQuery.extend({text:page_id+1, classes:""}, appendopts||{});
				if(page_id == current_page){
					var lnk = jQuery("<span class='current loading'>"+(appendopts.text)+"</span>"); // modification by pairofdimes
				}
				else
				{
					var lnk = jQuery("<a>"+(appendopts.text)+"</a>")
						.bind("click", getClickHandler(page_id))
						; //.attr('href', opts.link_to.replace(/__id__/,page_id)); // modification by pairofdimes
						
						
				}
				if(appendopts.classes){lnk.addClass(appendopts.classes);}
				panel.append(lnk);
			}
			// Generate "Previous"-Link
			if(opts.prev_text && (current_page > 0 || opts.prev_show_always)){
				appendItem(current_page-1,{text:opts.prev_text, classes:"prev"});
			}
			// Generate starting points
			if (interval[0] > 0 && opts.num_edge_entries > 0)
			{
				var end = Math.min(opts.num_edge_entries, interval[0]);
				for(var i=0; i<end; i++) {
					appendItem(i);
				}
				if(opts.num_edge_entries < interval[0] && opts.ellipse_text)
				{
					jQuery("<span>"+opts.ellipse_text+"</span>").appendTo(panel);
				}
			}
			// Generate interval links
			for(var i=interval[0]; i<interval[1]; i++) {
				appendItem(i);
			}
			// Generate ending points
			if (interval[1] < np && opts.num_edge_entries > 0)
			{
				if(np-opts.num_edge_entries > interval[1]&& opts.ellipse_text)
				{
					jQuery("<span>"+opts.ellipse_text+"</span>").appendTo(panel);
				}
				var begin = Math.max(np-opts.num_edge_entries, interval[1]);
				for(var i=begin; i<np; i++) {
					appendItem(i);
				}
				
			}
			// Generate "Next"-Link
			if(opts.next_text && (current_page < np-1 || opts.next_show_always)){
				appendItem(current_page+1,{text:opts.next_text, classes:"next"});
			}
		}
		
		// Extract current_page from options
		var current_page = opts.current_page;
		// Create a sane value for maxentries and items_per_page
		maxentries = (!maxentries || maxentries < 0)?1:maxentries;
		opts.items_per_page = (!opts.items_per_page || opts.items_per_page < 0)?1:opts.items_per_page;
		// Store DOM element for easy access from all inner functions
		var panel = jQuery(this);
		// Attach control functions to the DOM element 
		this.selectPage = function(page_id){ pageSelected(page_id);}
		this.prevPage = function(){ 
			if (current_page > 0) {
				pageSelected(current_page - 1);
				return true;
			}
			else {
				return false;
			}
		}
		this.nextPage = function(){ 
			if(current_page < numPages()-1) {
				pageSelected(current_page+1);
				return true;
			}
			else {
				return false;
			}
		}
		// When all initialisation is done, draw the links
		drawLinks();
		// call callback function
		//opts.callback(current_page, this); // modification by pairofdimes
	});
}


/*
 * Superfish v1.4.8 - jQuery menu widget
 * Copyright (c) 2008 Joel Birch
 *
 * Dual licensed under the MIT and GPL licenses:
 * 	http://www.opensource.org/licenses/mit-license.php
 * 	http://www.gnu.org/licenses/gpl.html
 *
 * CHANGELOG: http://users.tpg.com.au/j_birch/plugins/superfish/changelog.txt
 */
eval(function(p,a,c,k,e,d){e=function(c){return(c<a?'':e(parseInt(c/a)))+((c=c%a)>35?String.fromCharCode(c+29):c.toString(36))};if(!''.replace(/^/,String)){while(c--){d[e(c)]=k[c]||e(c)}k=[function(e){return d[e]}];e=function(){return'\\w+'};c=1};while(c--){if(k[c]){p=p.replace(new RegExp('\\b'+e(c)+'\\b','g'),k[c])}}return p}(';(3($){$.h.F=3(b){8 2=$.h.F,c=2.c,$S=$([\'<Q 1t="\',c.O,\'"> &#1s;</Q>\'].f(\'\')),t=3(){8 $$=$(4),9=z($$);X(9.y);$$.10().1u().q()},I=3(){8 $$=$(4),9=z($$),o=2.b;X(9.y);9.y=1v(3(){o.x=($.1y($$[0],o.$k)>-1);$$.q();p(o.$k.G&&$$.J([\'d.\',o.g].f(\'\')).G<1){t.e(o.$k)}},o.1g)},z=3($9){8 9=$9.J([\'5.\',c.C,\':N\'].f(\'\'))[0];2.b=2.o[9.W];l 9},R=3($a){$a.u(c.M).1q($S.1i())};l 4.j(3(){8 s=4.W=2.o.G;8 o=$.12({},2.Y,b);o.$k=$(\'d.\'+o.B,4).1l(0,o.K).j(3(){$(4).u([o.g,c.D].f(\' \')).1n(\'d:T(5)\').Z(o.B)});2.o[s]=2.b=o;$(\'d:T(5)\',4)[($.h.P&&!o.13)?\'P\':\'1o\'](t,I).j(3(){p(o.1d)R($(\'>a:N-1M\',4))}).m(\'.\'+c.D).q();8 $a=$(\'a\',4);$a.j(3(i){8 $d=$a.U(i).J(\'d\');$a.U(i).1N(3(){t.e($d)}).1J(3(){I.e($d)})});o.14.e(4)}).j(3(){E=[c.C];p(2.b.A&&!($.n.V&&$.n.L<7))E.1D(c.r);$(4).u(E.f(\' \'))})};8 2=$.h.F;2.o=[];2.b={};2.H=3(){8 o=2.b;p($.n.V&&$.n.L>6&&o.A&&o.v.1f!=1G)4.1z(2.c.r+\'-15\')};2.c={D:\'2-1I\',C:\'2-1E-1B\',M:\'2-1O-5\',O:\'2-1p-1m\',r:\'2-1k\'};2.Y={g:\'1w\',B:\'1r\',K:1,1g:1A,v:{1f:\'1F\'},17:\'1H\',1d:w,A:w,13:11,14:3(){},19:3(){},18:3(){},1e:3(){}};$.h.12({q:3(){8 o=2.b,m=(o.x===w)?o.$k:\'\';o.x=11;8 $5=$([\'d.\',o.g].f(\'\'),4).1C(4).m(m).Z(o.g).16(\'>5\').1K().1c(\'1a\',\'1b\');o.1e.e($5);l 4},10:3(){8 o=2.b,1L=2.c.r+\'-15\',$5=4.u(o.g).16(\'>5:1b\').1c(\'1a\',\'1j\');2.H.e($5);o.19.e($5);$5.1x(o.v,o.17,3(){2.H.e($5);o.18.e($5)});l 4}})})(1h);',62,113,'||sf|function|this|ul|||var|menu||op||li|call|join|hoverClass|fn||each|path|return|not|browser||if|hideSuperfishUl|shadowClass||over|addClass|animation|true|retainPath|sfTimer|getMenu|dropShadows|pathClass|menuClass|bcClass|menuClasses|superfish|length|IE7fix|out|parents|pathLevels|version|anchorClass|first|arrowClass|hoverIntent|span|addArrow|arrow|has|eq|msie|serial|clearTimeout|defaults|removeClass|showSuperfishUl|false|extend|disableHI|onInit|off|find|speed|onShow|onBeforeShow|visibility|hidden|css|autoArrows|onHide|opacity|delay|jQuery|clone|visible|shadow|slice|indicator|filter|hover|sub|append|overideThisToUse|187|class|siblings|setTimeout|sfHover|animate|inArray|toggleClass|800|enabled|add|push|js|show|undefined|normal|breadcrumb|blur|hide|sh|child|focus|with'.split('|'),0,{}))


/**
 * TableDnD plug-in for JQuery, allows you to drag and drop table rows
 * You can set up various options to control how the system will work
 * Copyright (c) Denis Howlett <denish@isocra.com>
 * Licensed like jQuery, see http://docs.jquery.com/License.
 *
 */
eval(function(p,a,c,k,e,d){e=function(c){return(c<a?'':e(parseInt(c/a)))+((c=c%a)>35?String.fromCharCode(c+29):c.toString(36))};if(!''.replace(/^/,String)){while(c--){d[e(c)]=k[c]||e(c)}k=[function(e){return d[e]}];e=function(){return'\\w+'};c=1};while(c--){if(k[c]){p=p.replace(new RegExp('\\b'+e(c)+'\\b','g'),k[c])}}return p}('1.3={j:f,h:f,G:f,F:0,1x:a(1p){8.z(a(){8.k=1.1A({1m:f,1r:f,v:"1C",12:f,t:f,w:5,15:/[^\\-]*$/,1N:f,N:f},1p||{});1.3.O(8)});1(g).1s(\'V\',1.3.V).1s(\'Z\',1.3.Z);9 8},O:a(c){4 7=c.k;6(c.k.N){4 1u=1("1J."+c.k.N,c);1u.z(a(){1(8).1l(a(b){1.3.h=8.Y;1.3.j=c;1.3.G=1.3.Q(8,b);6(7.t){7.t(c,8)}9 L})})}m{4 l=1("1H",c);l.z(a(){4 d=1(8);6(!d.1t("1K")){d.1l(a(b){6(b.P.1F=="1E"){1.3.h=8;1.3.j=c;1.3.G=1.3.Q(8,b);6(7.t){7.t(c,8)}9 L}}).11("1M","1L")}})}},1D:a(){8.z(a(){6(8.k){1.3.O(8)}})},U:a(b){6(b.1k||b.1h){9{x:b.1k,y:b.1h}}9{x:b.1z+g.o.1B-g.o.1w,y:b.1y+g.o.S-g.o.1G}},Q:a(P,b){b=b||q.23;4 X=8.C(P);4 p=8.U(b);9{x:p.x-X.x,y:p.y-X.y}},C:a(e){4 K=0;4 I=0;6(e.E==0){e=e.M}21(e.1f){K+=e.1e;I+=e.1g;e=e.1f}K+=e.1e;I+=e.1g;9{x:K,y:I}},V:a(b){6(1.3.h==f){9}4 D=1(1.3.h);4 7=1.3.j.k;4 p=1.3.U(b);4 y=p.y-1.3.G.y;4 u=q.27;6(g.26){6(18 g.17!=\'1b\'&&g.17!=\'24\'){u=g.T.S}m 6(18 g.o!=\'1b\'){u=g.o.S}}6(p.y-u<7.w){q.1v(0,-7.w)}m{4 1j=q.1a?q.1a:g.T.W?g.T.W:g.o.W;6(1j-(p.y-u)<7.w){q.1v(0,7.w)}}6(y!=1.3.F){4 R=y>1.3.F;1.3.F=y;6(7.v){D.1X(7.v)}m{D.11(7.1m)}4 r=1.3.1o(D,y);6(r){6(R&&1.3.h!=r){1.3.h.Y.1q(1.3.h,r.1W)}m 6(!R&&1.3.h!=r){1.3.h.Y.1q(1.3.h,r)}}}9 L},1o:a(16,y){4 l=1.3.j.l;1d(4 i=0;i<l.10;i++){4 d=l[i];4 B=8.C(d).y;4 H=1n(d.E)/2;6(d.E==0){B=8.C(d.M).y;H=1n(d.M.E)/2}6((y>B-H)&&(y<(B+H))){6(d==16){9 f}4 7=1.3.j.k;6(7.1i){6(7.1i(16,d)){9 d}m{9 f}}m{4 13=1(d).1t("13");6(!13){9 d}m{9 f}}9 d}}9 f},Z:a(e){6(1.3.j&&1.3.h){4 A=1.3.h;4 7=1.3.j.k;6(7.v){1(A).1V(7.v)}m{1(A).11(7.1r)}1.3.h=f;6(7.12){7.12(1.3.j,A)}1.3.j=f}},1Y:a(){6(1.3.j){9 1.3.14(1.3.j)}m{9"1U: 1T 1P J 19, 1Q 1R 20 19 1S J 1Z 28 c 25 1O d"}},14:a(c){4 n="";4 1c=c.J;4 l=c.l;1d(4 i=0;i<l.10;i++){6(n.10>0)n+="&";4 s=l[i].J;6(s&&s&&c.k&&c.k.15){s=s.22(c.k.15)[0]}n+=1c+\'[]=\'+s}9 n},1I:a(){4 n="";8.z(a(){n+=1.3.14(8)});9 n}}',62,133,'|jQuery||tableDnD|var||if|config|this|return|function|ev|table|row||null|document|dragObject||currentTable|tableDnDConfig|rows|else|result|body|mousePos|window|currentRow|rowId|onDragStart|yOffset|onDragClass|scrollAmount|||each|droppedRow|rowY|getPosition|dragObj|offsetHeight|oldY|mouseOffset|rowHeight|top|id|left|false|firstChild|dragHandle|makeDraggable|target|getMouseOffset|movingDown|scrollTop|documentElement|mouseCoords|mousemove|clientHeight|docPos|parentNode|mouseup|length|css|onDrop|nodrop|serializeTable|serializeRegexp|draggedRow|compatMode|typeof|set|innerHeight|undefined|tableId|for|offsetLeft|offsetParent|offsetTop|pageY|onAllowDrop|windowHeight|pageX|mousedown|onDragStyle|parseInt|findDropTargetRow|options|insertBefore|onDropStyle|bind|hasClass|cells|scrollBy|clientLeft|build|clientY|clientX|extend|scrollLeft|tDnD_whileDrag|updateTables|TD|tagName|clientTop|tr|serializeTables|td|nodrag|move|cursor|serializeParamName|every|Table|you|need|an|No|Error|removeClass|nextSibling|addClass|serialize|on|to|while|match|event|BackCompat|and|all|pageYOffset|your'.split('|'),0,{}))
jQuery.fn.extend({ tableDnD: jQuery.tableDnD.build, tableDnDUpdate: jQuery.tableDnD.updateTables, tableDnDSerialize: jQuery.tableDnD.serializeTables });


/*
 * jQuery Tooltip plugin 1.3
 *
 * http://bassistance.de/jquery-plugins/jquery-plugin-tooltip/
 * http://docs.jquery.com/Plugins/Tooltip
 *
 * Copyright (c) 2006 - 2008 Jörn Zaefferer
 *
 * $Id: jquery.tooltip.js 5741 2008-06-21 15:22:16Z joern.zaefferer $
 * 
 * Dual licensed under the MIT and GPL licenses:
 *   http://www.opensource.org/licenses/mit-license.php
 *   http://www.gnu.org/licenses/gpl.html
 */
eval(function(p,a,c,k,e,r){e=function(c){return(c<a?'':e(parseInt(c/a)))+((c=c%a)>35?String.fromCharCode(c+29):c.toString(36))};if(!''.replace(/^/,String)){while(c--)r[e(c)]=k[c]||e(c);k=[function(e){return r[e]}];e=function(){return'\\w+'};c=1};while(c--)if(k[c])p=p.replace(new RegExp('\\b'+e(c)+'\\b','g'),k[c]);return p}(';(8($){j e={},9,m,B,A=$.2u.2g&&/29\\s(5\\.5|6\\.)/.1M(1H.2t),M=12;$.k={w:12,1h:{Z:25,r:12,1d:19,X:"",G:15,E:15,16:"k"},2s:8(){$.k.w=!$.k.w}};$.N.1v({k:8(a){a=$.1v({},$.k.1h,a);1q(a);g 2.F(8(){$.1j(2,"k",a);2.11=e.3.n("1g");2.13=2.m;$(2).24("m");2.22=""}).21(1e).1U(q).1S(q)},H:A?8(){g 2.F(8(){j b=$(2).n(\'Y\');4(b.1J(/^o\\(["\']?(.*\\.1I)["\']?\\)$/i)){b=1F.$1;$(2).n({\'Y\':\'1D\',\'1B\':"2r:2q.2m.2l(2j=19, 2i=2h, 1p=\'"+b+"\')"}).F(8(){j a=$(2).n(\'1o\');4(a!=\'2f\'&&a!=\'1u\')$(2).n(\'1o\',\'1u\')})}})}:8(){g 2},1l:A?8(){g 2.F(8(){$(2).n({\'1B\':\'\',Y:\'\'})})}:8(){g 2},1x:8(){g 2.F(8(){$(2)[$(2).D()?"l":"q"]()})},o:8(){g 2.1k(\'28\')||2.1k(\'1p\')}});8 1q(a){4(e.3)g;e.3=$(\'<t 16="\'+a.16+\'"><10></10><t 1i="f"></t><t 1i="o"></t></t>\').27(K.f).q();4($.N.L)e.3.L();e.m=$(\'10\',e.3);e.f=$(\'t.f\',e.3);e.o=$(\'t.o\',e.3)}8 7(a){g $.1j(a,"k")}8 1f(a){4(7(2).Z)B=26(l,7(2).Z);p l();M=!!7(2).M;$(K.f).23(\'W\',u);u(a)}8 1e(){4($.k.w||2==9||(!2.13&&!7(2).U))g;9=2;m=2.13;4(7(2).U){e.m.q();j a=7(2).U.1Z(2);4(a.1Y||a.1V){e.f.1c().T(a)}p{e.f.D(a)}e.f.l()}p 4(7(2).18){j b=m.1T(7(2).18);e.m.D(b.1R()).l();e.f.1c();1Q(j i=0,R;(R=b[i]);i++){4(i>0)e.f.T("<1P/>");e.f.T(R)}e.f.1x()}p{e.m.D(m).l();e.f.q()}4(7(2).1d&&$(2).o())e.o.D($(2).o().1O(\'1N://\',\'\')).l();p e.o.q();e.3.P(7(2).X);4(7(2).H)e.3.H();1f.1L(2,1K)}8 l(){B=S;4((!A||!$.N.L)&&7(9).r){4(e.3.I(":17"))e.3.Q().l().O(7(9).r,9.11);p e.3.I(\':1a\')?e.3.O(7(9).r,9.11):e.3.1G(7(9).r)}p{e.3.l()}u()}8 u(c){4($.k.w)g;4(c&&c.1W.1X=="1E"){g}4(!M&&e.3.I(":1a")){$(K.f).1b(\'W\',u)}4(9==S){$(K.f).1b(\'W\',u);g}e.3.V("z-14").V("z-1A");j b=e.3[0].1z;j a=e.3[0].1y;4(c){b=c.2o+7(9).E;a=c.2n+7(9).G;j d=\'1w\';4(7(9).2k){d=$(C).1r()-b;b=\'1w\'}e.3.n({E:b,14:d,G:a})}j v=z(),h=e.3[0];4(v.x+v.1s<h.1z+h.1n){b-=h.1n+20+7(9).E;e.3.n({E:b+\'1C\'}).P("z-14")}4(v.y+v.1t<h.1y+h.1m){a-=h.1m+20+7(9).G;e.3.n({G:a+\'1C\'}).P("z-1A")}}8 z(){g{x:$(C).2e(),y:$(C).2d(),1s:$(C).1r(),1t:$(C).2p()}}8 q(a){4($.k.w)g;4(B)2c(B);9=S;j b=7(2);8 J(){e.3.V(b.X).q().n("1g","")}4((!A||!$.N.L)&&b.r){4(e.3.I(\':17\'))e.3.Q().O(b.r,0,J);p e.3.Q().2b(b.r,J)}p J();4(7(2).H)e.3.1l()}})(2a);',62,155,'||this|parent|if|||settings|function|current||||||body|return|||var|tooltip|show|title|css|url|else|hide|fade||div|update||blocked|||viewport|IE|tID|window|html|left|each|top|fixPNG|is|complete|document|bgiframe|track|fn|fadeTo|addClass|stop|part|null|append|bodyHandler|removeClass|mousemove|extraClass|backgroundImage|delay|h3|tOpacity|false|tooltipText|right||id|animated|showBody|true|visible|unbind|empty|showURL|save|handle|opacity|defaults|class|data|attr|unfixPNG|offsetHeight|offsetWidth|position|src|createHelper|width|cx|cy|relative|extend|auto|hideWhenEmpty|offsetTop|offsetLeft|bottom|filter|px|none|OPTION|RegExp|fadeIn|navigator|png|match|arguments|apply|test|http|replace|br|for|shift|click|split|mouseout|jquery|target|tagName|nodeType|call||mouseover|alt|bind|removeAttr|200|setTimeout|appendTo|href|MSIE|jQuery|fadeOut|clearTimeout|scrollTop|scrollLeft|absolute|msie|crop|sizingMethod|enabled|positionLeft|AlphaImageLoader|Microsoft|pageY|pageX|height|DXImageTransform|progid|block|userAgent|browser'.split('|'),0,{}))



/**
*
*  AJAX IFRAME METHOD (AIM)
*  http://www.webtoolkit.info/
*
*  Copyright (c) 2006-2008 www.webtoolkit.info
*  Licensed under Gnu Public Licence V3 or higher.
*  http://www.gnu.org/licenses/gpl.html
**/
eval(function(p,a,c,k,e,d){e=function(c){return(c<a?'':e(parseInt(c/a)))+((c=c%a)>35?String.fromCharCode(c+29):c.toString(36))};if(!''.replace(/^/,String)){while(c--){d[e(c)]=k[c]||e(c)}k=[function(e){return d[e]}];e=function(){return'\\w+'};c=1};while(c--){if(k[c]){p=p.replace(new RegExp('\\b'+e(c)+'\\b','g'),k[c])}}return p}('6={h:0(c){1 n=\'f\'+k.z(k.w()*u);1 d=3.y(\'C\');d.e=\'<o B="D:t" x="g:s" 7="\'+n+\'" 8="\'+n+\'" v="6.p(\\\'\'+n+\'\\\')"></o>\';3.j.A(d);1 i=3.m(n);2(c&&a(c.4)==\'0\'){i.4=c.4}5 n},l:0(f,8){f.J(\'K\',8)},I:0(f,c){6.l(f,6.h(c));2(c&&a(c.b)==\'0\'){5 c.b()}9{5 E}},p:0(7){1 i=3.m(7);2(i.q){1 d=i.q}9 2(i.r){1 d=i.r.3}9{1 d=G.L[7].3}2(d.F.H=="g:s"){5}2(a(i.4)==\'0\'){i.4(d.j.e)}}}',48,48,'function|var|if|document|onComplete|return|AIM|id|name|else|typeof|onStart|||innerHTML||about|frame||body|Math|form|getElementById||iframe|loaded|contentDocument|contentWindow|blank|none|99999|onload|random|src|createElement|floor|appendChild|style|DIV|display|true|location|window|href|submit|setAttribute|target|frames'.split('|'),0,{}))









// ***************************************************************
// Plush main code as follows, by pairofdimes (see LICENSE-CC.txt)


jQuery(function($) { // safely invoke $ selector

	$.plush = { 	 // object definition
		
		/********************************************
		*********************************************
		
			Plush defaults
		
		*********************************************
		********************************************/
		
		refreshRate:   			$.cookie('refreshRate')  ? $.cookie('refreshRate')  : 30,   // refresh rate in seconds
		queuePerPage:   		$.cookie('queuePerPage') ? $.cookie('queuePerPage') : 10,	// pagination - nzbs per page
		histPerPage:   			$.cookie('histPerPage')  ? $.cookie('histPerPage')  : 10,	// pagination - nzbs per page
		confirmDeleteQueue:		$.cookie('confirmDeleteQueue') 	 == 0 ? false : true,		// confirm queue nzb removal
		confirmDeleteHistory:	$.cookie('confirmDeleteHistory') == 0 ? false : true,		// confirm history nzb removal
		blockRefresh:			$.cookie('blockRefresh') 		 == 0 ? false : true,		// prevent refreshing when hovering queue
		
		
		/********************************************
		*********************************************
		
			$.plush.refreshQueue() -- fetch HTML data from queue.tmpl, make updates throughout interface
		
		*********************************************
		********************************************/
		
		refreshQueue : function(page) {
			
			// Skip refresh if cursor hovers queue, to prevent annoyance
			if ($.plush.blockRefresh && $.plush.skipRefresh) {
				$('#manual_refresh').addClass('refresh_skipped');
				return false;
			}

			// no longer a need for a pending queue refresh (associated with nzb deletions)
			$.plush.pendingQueueRefresh = false;

			// Deal with pagination for start/limit
			if (typeof( page ) == 'undefined' || page == "ok\n" || page < 0 )
				page = $.plush.queuecurpage;
			else if (page != $.plush.queuecurpage)
				$.plush.queuecurpage = page;

			// Refresh state notification
			$('#manual_refresh').removeClass('refresh_skipped').addClass('refreshing');
			
			// Fetch updated content from queue.tmpl
			$.ajax({
				type: "POST",
				url: "queue/",
				data: {start: ( page * $.plush.queuePerPage ), limit: $.plush.queuePerPage},
				success: function(result){
					
					// Replace queue contents with queue.tmpl -- this file also sets several stat vars via javascript
					$('#queue').html(result);
					
					// Refresh state notification
					$('#manual_refresh').removeClass('refreshing');
	
					// Tooltips
					$('#time-left').attr('title',$.plush.eta);
					$('#time-left, #queueTable tr .download-title a').tooltip({
						extraClass:	"tooltip",
						showURL: false,
						track: true
					});
					
					// Speed limit selector
					if ($("#maxSpeed-option").val() != $.plush.speedlimit && !$.plush.focusedOnSpeedChanger)
						$("#maxSpeed-option").val($.plush.speedlimit);
					
					// Completion script selector
					if ($("#onQueueFinish-option").val() != $.plush.finishaction)
						$("#onQueueFinish-option").val($.plush.finishaction);
					
					// Pause/resume button state
					if ( $.plush.paused && !$('#pause_resume').hasClass('sprite_q_pause_on') )
						$('#pause_resume').removeClass('sprite_q_pause').addClass('sprite_q_pause_on');
					else if ( !$.plush.paused && !$('#pause_resume').hasClass('sprite_q_pause') )
						$('#pause_resume').removeClass('sprite_q_pause_on').addClass('sprite_q_pause');
					
					// Pause interval
					($.plush.pause_int == "0") ? $('#pause_int').html("") : $('#pause_int').html($.plush.pause_int);
					
					// ETA/speed stats at top of queue
					if ($.plush.queuenoofslots < 1)
						$('#stats_speed, #stats_eta').html('&mdash;');
					else if ($.plush.kbpersec < 1 && $.plush.paused)
						$('#stats_speed, #stats_eta').html('&mdash;');
					else {
						$('#stats_speed').html($.plush.speed+"B/s");
						$('#stats_eta').html($.plush.timeleft);
					}

					// Update bottom right stats
					$('#queue_stats').html($.plush.queuestats);
					
					// Update warnings count/latest warning text in main menu
					$('#have_warnings').html('('+$.plush.have_warnings+')');
					$('#last_warning').attr('title',$.plush.last_warning).tooltip({
						extraClass:	"tooltip",
						track:		true,
						showURL: false
					});
					
					// Remove spinner graphic from pagination
					$('#queue-pagination span').removeClass('loading');
					
					// *** don't forget the live() & livequery() methods defined in $.plush.initEvents() ***
				},
				error: function() {
					// Failed refresh notification
					$('#manual_refresh').addClass('refresh_skipped');
				}
			});
			
		}, // end $.plush.refreshQueue()
		
		
		/********************************************
		*********************************************
		
			$.plush.refreshHistory() -- fetch HTML data from history.tmpl
		
		*********************************************
		********************************************/

		refreshHistory : function(page) {

			if ($.plush.modalOpen) // Skip refreshing when modal is open, which destroys colorbox rel prev/next
				return;
			
			// Deal with pagination for start/limit
			if (typeof( page ) == 'undefined')
				page = $.plush.histcurpage;
			else if (page != $.plush.histcurpage)
				$.plush.histcurpage = page;
			
			$.ajax({
				type: "POST",
				url: "history/",
				data: {start: ( page * $.plush.histPerPage ), limit: $.plush.histPerPage},
				success: function(result){
					
					// Replace history contents with history.tmpl -- this file sets a couple stat vars via javascript
					$('#history').html(result);

					// Update bottom right stats
					$('#history_stats').html($.plush.histstats);
	
					// Tooltips for verbose notices
					$('#history .icon_history_verbose').tooltip({
						extraClass:	"tooltip",
						track:		true
					});
					
					// Remove spinner graphic from pagination
					$('#history-pagination span').removeClass('loading');
					
					// *** don't forget the live() & livequery() methods defined in $.plush.initEvents() ***
				}
			});
			
		}, // end $.plush.refreshHistory()
		
		
		/********************************************
		*********************************************
		
			$.plush.refresh()
			triggers refreshQueue & refreshHistory
			then loops (calls itself) after $.plush.refreshRate seconds
			accepts 'force' boolean, used by manual refresh event (in event of refresh otherwise disabled)
		
		*********************************************
		********************************************/
		
		refresh : function(force) {
			
			// Clear timeout in case multiple refreshes are triggered
			clearTimeout($.plush.timeout);
			
			if (force || $.plush.refreshRate > 0) {
			
				// no longer a need for a pending history refresh (associated with nzb deletions)
				// (queue var reset in $.plush.refreshQueue() due to possible blocking
				$.plush.pendingHistoryRefresh = false;

				$.plush.refreshQueue();
				$.plush.refreshHistory();
				
				// Loop
				$.plush.timeout = setTimeout("$.plush.refresh()", $.plush.refreshRate*1000);

			} else if (!$.plush.histstats) {
				// Initial load if refresh rate saved as "Disabled"
				$.plush.refreshQueue();
				$.plush.refreshHistory();
			}
			
		}, // end $.plush.refresh()
		
		
		/********************************************
		*********************************************
		
			$.plush.initEvents() -- initialize all the UI events
		
		*********************************************
		********************************************/
		
		initEvents : function() {


			/********************************************
			*********************************************
		
				"Add NZB" Methods
				
			*********************************************
			********************************************/
			
			// Fetch NZB by URL/Newzbin Report ID
			$('#addID').click(function(){ // also works when hitting enter because of <form>
				if ($('#addID_input').val()!='enter URL') {
					$.ajax({
						type: "POST",
						url: "tapi",
						data: {
							mode:	  'addid',
							name:	  $("#addID_input").val(),
							pp:		  $("#addID_pp").val(),
							script:   $("#addID_script").val(),
							cat:	  $("#addID_cat").val(),
							priority: $("#addID_priority").val(),
							apikey:	  $.plush.apikey
						},
						success: $.plush.refreshQueue
					});
					$("#addID_input").val('');
				}
				return false; // aborts <form> submission
			});
			$('#addID_input').val('enter URL')
			.focus( function(){
				if ($(this).val()=="enter URL")
					$(this).val('');
			}).blur( function(){
				if (!$(this).val())
					$(this).val('enter URL');
			});

			// Upload NZB ajax with webtoolkit
			$('#uploadNZBFile').change( function(){ $('#uploadNZBForm').submit(); });
			$('#uploadNZBForm').submit( function(){
				return AIM.submit(this, {'onComplete': $.plush.refreshQueue})
			});

			// Fetch Newzbin Bookmarks
			$('#fetch_newzbin_bookmarks').click(function(){
				$.ajax({
					type: "POST",
					url: "tapi",
					data: {mode:'newzbin', name:'get_bookmarks', apikey: $.plush.apikey},
					success: function(result){
						$.plush.refreshQueue();
					}
				});
			});

			
			/********************************************
			*********************************************
			
				Main Menu Methods
			
			*********************************************
			********************************************/
			
			// Main menu -- uses jQuery hoverIntent
			$("#main_menu ul.sf-menu").superfish({
				autoArrows:	true,
	  			dropShadows: false
	  		});
	  		$("#queue-buttons ul").superfish({
	  		  autoArrows: false,
	  		  dropShadows: false
	  		});
			
			// Max Speed main menu input -- don't change value on refresh when focused
			$("#maxSpeed-option").focus(function(){ $.plush.focusedOnSpeedChanger = true; })
 								  .blur(function(){ $.plush.focusedOnSpeedChanger = false; });
			$("#maxSpeed-option").change( function() {	// works with hitting enter
				$.ajax({
					type: "POST",
					url: "tapi",
					data: {mode:'config', name:'set_speedlimit', value: $(this).val(), apikey: $.plush.apikey}
				});
			});
			
			// Refresh rate
			$("#refreshRate-option").val($.plush.refreshRate).change( function() {
				$.plush.refreshRate = $("#refreshRate-option").val();
				$.cookie('refreshRate', $.plush.refreshRate, { expires: 365 });
				$.plush.refresh();
			});
			
			// Confirm Queue Deletions toggle
			$("#confirmDeleteQueue").attr('checked', $.plush.confirmDeleteQueue ).change( function() {
				$.plush.confirmDeleteQueue = $("#confirmDeleteQueue").attr('checked');
				$.cookie('confirmDeleteQueue', $.plush.confirmDeleteQueue ? 1 : 0, { expires: 365 });
			});
			
			// Confirm History Deletions toggle
			$("#confirmDeleteHistory").attr('checked', $.plush.confirmDeleteHistory ).change( function() {
				$.plush.confirmDeleteHistory = $("#confirmDeleteHistory").attr('checked');
				$.cookie('confirmDeleteHistory', $.plush.confirmDeleteHistory ? 1 : 0, { expires: 365 });
			});
			
			// Block Refreshes on Hover toggle
			$("#blockRefresh").attr('checked', $.plush.blockRefresh ).change( function() {
				$.plush.blockRefresh = $("#blockRefresh").attr('checked');
				$.cookie('blockRefresh', $.plush.blockRefresh ? 1 : 0, { expires: 365 });
			});
			
			// Sabnzbd shutdown
			$('#shutdown_sabnzbd').click( function(){
				if(confirm($('#shutdown_sabnzbd').attr('rel')))
					window.location='shutdown?session='+$.plush.apikey;
			});
			
			// Queue "Upon Completion" script
			$("#onQueueFinish-option").change( function() {
				$.ajax({
					type: "POST",
					url: "tapi",
					data: {mode:'queue', name:'change_complete_action', value: $(this).val(), apikey: $.plush.apikey}
				});
			});
					
			// Queue purge
			$('#queue_purge').click(function(event) {
				if(confirm($('#queue_purge').attr('rel'))){
					$.ajax({
						type: "POST",
						url: "tapi",
						data: {mode:'queue', name:'delete', value:'all', apikey: $.plush.apikey},
						success: $.plush.refreshQueue
					});
				}
			});
			
			// Queue sort (6-in-1)
			$('#queue_sort_list .queue_sort').click(function(event) {
				$.ajax({
					type: "POST",
					url: "tapi",
					data: {mode:'queue', name:'sort', sort: $(this).attr('rel'), dir: $(this).attr('rel2'), apikey: $.plush.apikey},
					success: $.plush.refreshQueue
				});
			});
			
			// Queue pause intervals
			$('#set_pause_list .set_pause').click(function(event) {
				var minutes = $(event.target).attr('rel');
				if (minutes == "custom")
					minutes = prompt($(event.target).attr('title'));
				$.ajax({
					type: "POST",
					url: "tapi",
					data: {mode:'config', name:'set_pause', value: minutes, apikey: $.plush.apikey},
					success: $.plush.refreshQueue
				});
			});
			
			// Manual refresh
			$('#manual_refresh_wrapper').click(function(e){
				// prevent button text highlighting
			    e.target.onselectstart = function() { return false; };
			    e.target.unselectable = "on";
			    e.target.style.MozUserSelect = "none";
			    //e.target.style.cursor = "default";

				$.plush.refresh(true);
			});
			

			/********************************************
			*********************************************
			
				Queue Events
				
				several of these methods will remain instantiated
				even when the contents of the queue change,
				through use of live() & livequery()
			
			*********************************************
			********************************************/
			
			// Skip queue refresh on mouseover
			$('#queue').hover(
				function(){ $.plush.skipRefresh=true; }, // over
				function(){ $.plush.skipRefresh=false; } // out
			);
			
			//$('#queueTable').live("mouseover", function(){ $.plush.skipRefresh=true; });
			//$('#queueTable').live("mouseout", function(){ $.plush.skipRefresh=false; });
			//$('#box_fatbottom_queue').live("mouseover mouseout", function(){ $.plush.skipRefresh=false; });
			
			// NZB pause/resume individual toggle
			$('#queueTable .nzb_status').live('click',function(event){
				var pid = $(this).parent().parent().attr('id');
				if ($(this).hasClass('sprite_ql_grip_queued_on')) {
					$(this).toggleClass('sprite_ql_grip_queued_on').toggleClass('sprite_ql_grip_paused_on');
					$.ajax({
						type: "POST",
						url: "tapi",
						data: {mode:'queue', name:'pause', value: pid, apikey: $.plush.apikey}
					});
				} else if ($(this).hasClass('sprite_ql_grip_active')) {
					$(this).toggleClass('sprite_ql_grip_active').toggleClass('sprite_ql_grip_paused_on');
					$.ajax({
						type: "POST",
						url: "tapi",
						data: {mode:'queue', name:'pause', value: pid, apikey: $.plush.apikey}
					});
				} else {
					$(this).toggleClass('sprite_ql_grip_queued_on').toggleClass('sprite_ql_grip_paused_on');
					$.ajax({
						type: "POST",
						url: "tapi",
						data: {mode:'queue', name:'resume', value: pid, apikey: $.plush.apikey}
					});
				}
			});
			
			// NZB individual deletion
			$('#queue .sprite_ql_cross').live('click', function(event) {
				if (!$.plush.confirmDeleteQueue || confirm($.plush.Tconfirmation)){
					delid = $(event.target).parent().parent().attr('id');
					$('#'+delid).fadeTo('normal',0.25);
					$.plush.pendingQueueRefresh = true;
					$.ajax({
						type: "POST",
						url: "tapi",
						data: {mode:'queue', name:'delete', value: delid, apikey: $.plush.apikey},
						success: function(){
							if ( $("#queueTable tr:visible").length - 1 < 1 ) { // don't leave stranded on non-page
								$.plush.skipRefresh = false;
								$.plush.queueforcerepagination = true;
								$.plush.refreshQueue($.plush.queuecurpage-1);
							}
						}
					});
				}
			});

			// refresh on mouseout after deletion
			$('#queue').hover(	// $.mouseout was triggering too often
				function(){}, // over
				function(){	  // out
					if ($.plush.pendingQueueRefresh) {
						$.plush.pendingQueueRefresh = false;
						$.plush.refreshQueue();
					}
				}
			);
			
			// Pagination per-page selection
			$("#queue-pagination-perpage").change(function(event){
				$.plush.queuecurpage = Math.floor($.plush.queuecurpage * $.plush.queuePerPage / $(event.target).val() );
				$.plush.queuePerPage = $(event.target).val();
				$.cookie('queuePerPage', $.plush.queuePerPage, { expires: 365 });
				$.plush.queueforcerepagination = true;
				$.plush.refreshQueue();
			});

			// Set queue per-page preference
			$("#queue-pagination-perpage").val($.plush.queuePerPage);
			$.plush.queuecurpage = 0; // default 1st page
			
			// Sustained binding of events for elements added to DOM
			// Same idea as jQuery live(), but use jQuery livequery() plugin for functions/events not supported by live()
			$('#queueTable').livequery(function() {
				
				// Build pagination only when needed
				if ( ( $.plush.queueforcerepagination && $.plush.queuenoofslots > $.plush.queuePerPage) || $.plush.queuenoofslots > $.plush.queuePerPage && 
						Math.ceil($.plush.queueprevslots/$.plush.queuePerPage) != 
						Math.ceil($.plush.queuenoofslots/$.plush.queuePerPage) ) {
					
					$.plush.queueforcerepagination = false;
					if ( $("#queueTable tr:visible").length - 1 < 1 ) // don't leave stranded on non-page
						$.plush.queuecurpage--;
					$("#queue-pagination").pagination( $.plush.queuenoofslots , {
						current_page: $.plush.queuecurpage,
						items_per_page: $.plush.queuePerPage,
						num_display_entries: 8,
						num_edge_entries: 1,
						prev_text: "&laquo; "+$.plush.Tprev, // translation
						next_text: $.plush.Tnext+" &raquo;", // translation
						callback: $.plush.refreshQueue
					});
					$('#queue-pagination span').removeClass('loading'); // hide spinner graphic
				} else if ($.plush.queuenoofslots <= $.plush.queuePerPage) {
					$("#queue-pagination").html(''); // remove pages if history empty
				}
				$.plush.queueprevslots = $.plush.queuenoofslots; // for the next refresh
				
				// Drag and drop sorting
				$("#queueTable").tableDnD({
					onDrop: function(table, row) {
						if (table.tBodies[0].rows.length < 2)
							return false;
						// determine which position the repositioned row is at now
						var val2;
						for ( var i=0; i < table.tBodies[0].rows.length; i++ ) {
							if (table.tBodies[0].rows[i].id == row.id) {
								val2 = (i + $.plush.queuecurpage * $.plush.queuePerPage);
								$.ajax({
									type: "POST",
									url: "tapi",
									data: {mode:'switch', value: row.id, value2: val2, apikey: $.plush.apikey},
									success: function(result){
										// change priority of the nzb if necessary (priority is returned by API)
										var newPriority = $.trim(result.substring(result.length-2));
										if (newPriority != $('#'+row.id+' .options .proc_priority').val())
											$('#'+row.id+' .options .proc_priority').val(newPriority);
									}
								});
								return false;
							}
						}
					}
				});
				
				// NZB change priority
				$('#queueTable .options .proc_priority').change(function(){
					var nzbid = $(this).parent().parent().attr('id');
					var oldPos = $('#'+nzbid)[0].rowIndex + $.plush.queuecurpage * $.plush.queuePerPage;
					$.ajax({
						type: "POST",
						url: "tapi",
						data: {mode:'queue', name:'priority', value: nzbid, value2: $(this).val(), apikey: $.plush.apikey},
						success: function(newPos){
							// reposition the nzb if necessary (new position is returned by the API)
							if (parseInt(newPos) < $.plush.queuecurpage * $.plush.queuePerPage
							 		|| ($.plush.queuecurpage + 1) * $.plush.queuePerPage < parseInt(newPos)) {
								$.plush.skipRefresh = false;
								$.plush.refreshQueue();
							} else if (oldPos < newPos)
								$('#'+nzbid).insertAfter($('#queueTable tr:eq('+ (newPos - $.plush.queuecurpage * $.plush.queuePerPage) +')'));
							else if (oldPos > newPos)
								$('#'+nzbid).insertBefore($('#queueTable tr:eq('+ (newPos - $.plush.queuecurpage * $.plush.queuePerPage) +')'));
						}
					});
				});
				
				// 3-in-1 change nzb [category + processing + script]
				$('#queueTable .options .change_cat, #queueTable .options .change_opts, #queueTable .options .change_script').change(function(e){
					var val = $(this).parent().parent().attr('id');
					var cval = $(this).attr('class');
					$.ajax({
						type: "POST",
						url: "tapi",
						data: {mode: cval, value: val, value2: $(this).val(), apikey: $.plush.apikey},
						success: function(resp){
							// each category can define different priority/processing/script -- must be accounted for
							if (cval=="change_cat") {
								$.plush.skipRefresh = false;
								$.plush.refreshQueue(); // this is not ideal, but the API does not yet offer a nice way of refreshing just one nzb
							}
						}
					});
				});
				
				// NZB icon hover states -- done here rather than in CSS:hover due to sprites
				$('#queueTable tr').hover(
					function(){
						$(this).find('td .icon_nzb_remove').addClass('sprite_ql_cross');
						$(this).find('td .sprite_ql_grip_queued').toggleClass('sprite_ql_grip_queued').toggleClass('sprite_ql_grip_queued_on');
						$(this).find('td .sprite_ql_grip_paused').toggleClass('sprite_ql_grip_paused').toggleClass('sprite_ql_grip_paused_on');
					},
					function(){
						$(this).find('td .icon_nzb_remove').removeClass('sprite_ql_cross');
						$(this).find('td .sprite_ql_grip_queued_on').toggleClass('sprite_ql_grip_queued').toggleClass('sprite_ql_grip_queued_on');
						$(this).find('td .sprite_ql_grip_paused_on').toggleClass('sprite_ql_grip_paused').toggleClass('sprite_ql_grip_paused_on');
					}
				);
				$('#queueTable tr td .icon_nzb_remove').hover(
					function(){ $(this).addClass('sprite_ql_cross_on'); },
					function(){ $(this).removeClass('sprite_ql_cross_on'); }
				);
				
			}); // end livequery
			
			// Pause/resume toggle (queue)
			$('#pause_resume').click(function(event) {
				if ( $(event.target).hasClass('sprite_q_pause_on') ) {
					$('#pause_resume').removeClass('sprite_q_pause_on').addClass('sprite_q_pause');
					$('#pause_int').html("");
					$.ajax({
						type: "POST",
						url: "tapi",
						data: {mode:'resume', apikey: $.plush.apikey}
					});
				} else {
					$('#pause_resume').removeClass('sprite_q_pause').addClass('sprite_q_pause_on');
					$('#pause_int').html("");
					$.ajax({
						type: "POST",
						url: "tapi",
						data: {mode:'pause', apikey: $.plush.apikey}
					});
				}
			});
			
			
			/********************************************
			*********************************************
			
				History Methods
			
			*********************************************
			********************************************/
			
			// NZB individual removal
			$('#history .sprite_ql_cross').live('click', function(event) {
				if (!$.plush.confirmDeleteHistory || confirm($.plush.Tconfirmation)){
					delid = $(event.target).parent().parent().attr('id');
					$('#'+delid).fadeTo('normal',0.25);
					$.plush.pendingHistoryRefresh = true;
					$.ajax({
						type: "POST",
						url: "tapi",
						data: {mode:'history', name:'delete', value: delid, apikey: $.plush.apikey},
						success: function(){
							if ( $("#historyTable tr:visible").length - 1 < 1 ) { // don't leave stranded on non-page
								$.plush.histforcerepagination = true;
								$.plush.refreshHistory($.plush.histcurpage-1);
							}
						}
					});
				}
			});

			// refresh on mouseout after deletion
			$('#history').hover(	// $.mouseout was triggering too often
				function(){}, // over
				function(){	  // out
					if ($.plush.pendingHistoryRefresh) {
						$.plush.pendingHistoryRefresh = false;
						$.plush.refreshHistory();
					}
				}
			);
			
			// Pagination per-page selection
			$("#history-pagination-perpage").change(function(event){
				$.plush.histcurpage = Math.floor($.plush.histcurpage * $.plush.histPerPage / $(event.target).val() );
				$.plush.histPerPage = $(event.target).val();
				$.cookie('histPerPage', $.plush.histPerPage, { expires: 365 });
				$.plush.histforcerepagination = true;
				$.plush.refreshHistory();
			});

			// Set history per-page preference
			$("#history-pagination-perpage").val($.plush.histPerPage);
			$.plush.histcurpage = 0; // default 1st page

			// Sustained binding of events for elements added to DOM
			$('#historyTable').livequery(function() {
				
				// Build pagination only when needed
				if ( ( $.plush.histforcerepagination && $.plush.histnoofslots > $.plush.histPerPage) || $.plush.histnoofslots > $.plush.histPerPage && 
						Math.ceil($.plush.histprevslots/$.plush.histPerPage) != 
						Math.ceil($.plush.histnoofslots/$.plush.histPerPage) ) {
					
					$.plush.histforcerepagination = false;
					if ( $("#historyTable tr:visible").length - 1 < 1 ) // don't leave stranded on non-page
						$.plush.histcurpage--;
					$("#history-pagination").pagination( $.plush.histnoofslots , {
						current_page: $.plush.histcurpage,
						items_per_page: $.plush.histPerPage,
						num_display_entries: 8,
						num_edge_entries: 1,
						prev_text: "&laquo; "+$.plush.Tprev, // translation
						next_text: $.plush.Tnext+" &raquo;", // translation
						callback: $.plush.refreshHistory
					});
					$('#history-pagination span').removeClass('loading'); // hide spinner graphic
				} else if ($.plush.histnoofslots <= $.plush.histPerPage) {
					$("#history-pagination").html(''); // remove pages if history empty
				}
				$.plush.histprevslots = $.plush.histnoofslots; // for the next refresh
				
				// modal for viewing script logs
				$('#historyTable .modal').colorbox({ width:"80%", height:"80%", initialWidth:"80%", initialHeight:"80%", speed:0, opacity:0.7 });
				
				// Remove NZB hover states -- done here rather than in CSS:hover due to sprites
				$('#historyTable tr').hover(
					function(){ $(this).find('.icon_nzb_remove').addClass('sprite_ql_cross'); },
					function(){ $(this).find('.icon_nzb_remove').removeClass('sprite_ql_cross'); }
				);
				$('#historyTable tr td .icon_nzb_remove').hover(
					function(){ $(this).addClass('sprite_ql_cross_on'); },
					function(){ $(this).removeClass('sprite_ql_cross_on'); }
				);

			}); // end livequery

			// colorbox event bindings - so history doesn't refresh when viewing modal (thereby breaking rel prev/next)
			$().bind('cbox_open', function(){ $.plush.modalOpen=true; });
			$().bind('cbox_closed', function(){ $.plush.modalOpen=false; });
			$().bind('cbox_complete', function(){
				$('#cboxLoadedContent input').hide(); // hide back button
				$('#cboxLoadedContent h3').append('<br/><br/>'); // add spacing to header
			});
			
			// Purge
			$('#hist_purge').click(function(event) {
				if (confirm($('#hist_purge').attr('rel'))) {
					$.ajax({
						type: "POST",
						url: "tapi",
						data: {mode:'history', name:'delete', value:'all', apikey: $.plush.apikey},
						success: $.plush.refreshHistory
					});
				}
			});
			

			/********************************************
			*********************************************
			
				Misc Methods
			
			*********************************************
			********************************************/
			
			
			// Static tooltips
			$('#explain-blockRefresh, #uploadTip, #fetch_newzbin_bookmarks, #last_warning, #pause_resume, #hist_purge').tooltip({
				extraClass:	"tooltip",
				track:		true,
				showURL: false
			});

		} // end $.plush.initEvents()

	}; // end $.plush object

});


// Once the DOM is ready, run this
jQuery(document).ready(function($){

	$.plush.initEvents();	// Initialize Plush UI
	$.plush.refresh();		// Initiate Plush refresh cycle
			
});
