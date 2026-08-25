(function(){
"use strict";
var currentCat="ai",allItems=[],gamingHotspots=[],isRefreshing=false;
var importanceFilter="all",categoryFilter="all",contentTypeFilter="all",eventTypeFilter="all",searchQuery="";
var AI_CONTENT_CN={"updates":"动态","resources":"AI资源","trend":"趋势"};
var AI_CATEGORY_CN={"company":"企业动态","model_update":"模型更新","product_update":"产品/工具更新","breakthrough":"技术突破","agent":"Agent","model":"模型","tool":"工具","app":"应用","tech_direction":"技术方向","market_change":"市场变化","community_hotspot":"社区热点"};
var AI_SECONDARY={"updates":["company","model_update","product_update","breakthrough"],"resources":["agent","model","tool","app"],"trend":["tech_direction","market_change","community_hotspot"]};
var IMP={S:5,A:4,B:3,C:2,D:1};
var EVENT_CN={"Version Update":"版本更新","Season/Event":"赛季/活动","Character/Content":"角色/内容","Collaboration":"联动","Release":"发布","Community Hotspot":"社区热点","Industry":"行业","General":"资讯"};
var GAMING_EVENT_CN={"version_update":"版本更新","character_release":"角色上线","activity":"活动","esports":"赛事","season_event":"赛季/活动","character_content":"角色/内容","collaboration":"联动","release":"发布","community_hotspot":"社区热点","industry":"行业","general":"资讯"};
var tabs=document.querySelectorAll(".tab");
var newsList=document.getElementById("newsList");
var newsCount=document.getElementById("newsCount");
var newsUpdated=document.getElementById("newsUpdated");
var btnRefresh=document.getElementById("btnRefresh");
var statusDot=document.getElementById("statusDot");
var statusText=document.getElementById("statusText");
var dateDisplay=document.getElementById("dateDisplay");
var searchInput=document.getElementById("searchInput");
var searchClear=document.getElementById("searchClear");
var translations={};

function setStatus(s){
  statusDot.className="status-dot "+s;
  statusText.textContent={ready:"就绪",loading:"加载中...",error:"出错"}[s]||s;
}
function timeAgo(iso){
  var s=(Date.now()-new Date(iso).getTime())/1000;
  if(s<60)return"刚刚";
  var m=Math.floor(s/60);
  if(m<60)return m+"分钟前";
  var h=Math.floor(m/60);
  if(h<24)return h+"小时前";
  return Math.floor(h/24)+"天前";
}
function esc(t){if(!t)return"";var d=document.createElement("div");d.appendChild(document.createTextNode(t));return d.innerHTML;}

function matchQuery(it,q){
  q=(q||"").trim().toLowerCase();
  if(!q)return true;
  var tn=translations[it.id]||{};
  var fields=[it.title,it.summary,it.source,it.source_name,tn.title_cn,tn.summary_cn];
  for(var i=0;i<fields.length;i++){
    if(fields[i]&&String(fields[i]).toLowerCase().indexOf(q)!==-1)return true;
  }
  var tags=it.tags||[];
  for(var j=0;j<tags.length;j++){
    var label=typeof tags[j]==="string"?tags[j]:(tags[j].l||tags[j].name||tags[j].text||"");
    if(String(label).toLowerCase().indexOf(q)!==-1)return true;
  }
  return false;
}

function sortItems(items){
  return items.sort(function(a,b){
    var tn_a=translations[a.id],tn_b=translations[b.id];
    var ta=tn_a&&tn_a.status==='translated'?1:0;
    var tb=tn_b&&tn_b.status==='translated'?1:0;
    if(ta!==tb)return tb-ta;
    var va=a.value_score||0,vb=b.value_score||0;
    if(va!==vb)return vb-va;
    var ia=IMP[a.importance]||0,ib=IMP[b.importance]||0;
    if(ia!==ib)return ib-ia;
    var ha=a.hotness||0,hb=b.hotness||0;
    return hb-ha;
  });
}

function filterItems(items){
  return items.filter(function(it){
    if(importanceFilter!=="all"&&it.importance!==importanceFilter)return false;
    if(categoryFilter!=="all"&&it.category!==categoryFilter)return false;
    if(contentTypeFilter!=="all"&&currentCat==="ai"&&it.content_type!==contentTypeFilter)return false;
    if(eventTypeFilter!=="all"&&it.event_type!==eventTypeFilter)return false;
    if(!matchQuery(it,searchQuery))return false;
    return true;
  });
}

function filterGamingHotspots(){
  return gamingHotspots.filter(function(h){
    if(eventTypeFilter!=="all"&&h.event_type!==eventTypeFilter)return false;
    var q=(searchQuery||"").trim().toLowerCase();
    if(q&&String(h.game_name||"").toLowerCase().indexOf(q)===-1)return false;
    return true;
  });
}

function renderWithFilter(){
  if(currentCat==="gaming"){
    renderGamingHotspots(filterGamingHotspots());
    if(contentTypeFilter==="hotspot"){
      newsList.innerHTML="";
      newsCount.textContent="";
      return;
    }
  }
  renderItems(filterItems(allItems));
}

function buildFilters(){
  var fb=document.getElementById("filterBar");
  if(!fb)return;
  function btn(fName,v,label,active){
    return '<button class="fb-btn fb-'+fName+' '+(active?'active':'')+'" data-f="'+fName+'" data-v="'+esc(v)+'">'+esc(label)+'</button>';
  }
  var h='';
  if(currentCat==="ai"){
    h+='<div class="filter-row"><span class="filter-lbl">重要性:</span>';
    var imps=["all","S","A","B","C","D"];
    var impLabels={all:"全部",S:"S",A:"A",B:"B",C:"C",D:"D"};
    imps.forEach(function(v){h+=btn("imp",v,impLabels[v],importanceFilter===v);});
    h+='</div><div class="filter-row"><span class="filter-lbl">一级:</span>';
    var contents=[["all","全部"],["updates","动态"],["resources","AI资源"],["trend","趋势"]];
    contents.forEach(function(t){h+=btn("type",t[0],t[1],contentTypeFilter===t[0]);});
    h+='</div>';
    if(contentTypeFilter!=="all"){
      h+='<div class="filter-row"><span class="filter-lbl">二级:</span>';
      h+=btn("cat","all","全部",categoryFilter==="all");
      (AI_SECONDARY[contentTypeFilter]||[]).forEach(function(v){h+=btn("cat",v,AI_CATEGORY_CN[v]||v,categoryFilter===v);});
      h+='</div>';
    }
  }else{
    h+='<div class="filter-row"><span class="filter-lbl">类型:</span>';
    var types=[["all","全部"],["hotspot","运营热点"]];
    types.forEach(function(t){h+=btn("type",t[0],t[1],contentTypeFilter===t[0]);});
    h+='</div><div class="filter-row"><span class="filter-lbl">事件:</span>';
    var events=[["all","全部"],["version_update","版本更新"],["character_release","角色上线"],["activity","活动"],["esports","赛事"],["collaboration","联动"]];
    events.forEach(function(t){h+=btn("event",t[0],t[1],eventTypeFilter===t[0]);});
  }
  h+='</div>';
  fb.innerHTML=h;
}

function renderNewsCard(it){
  var tn=translations[it.id];
  var r=it.rank||0;
  var imp=it.importance||"";
  var isGitHub=String(it.source||"").toLowerCase()==="github";
  var ctName=it.content_type?AI_CONTENT_CN[it.content_type]:"";
  var catName=it.category?AI_CATEGORY_CN[it.category]||it.category:"";
  var tc=r===1?"top-1":r===2?"top-2":r===3?"top-3":"";
  var sc="imp-"+imp;
  var hc=it.hotness>=70?"high":it.hotness>=40?"mid":"low";
  var html='<div class="news-card '+tc+' '+sc+'">';
  html+='<div class="news-rank">'+r+'</div>';
  html+='<div class="news-body">';
  html+='<div class="news-title"><a href="'+esc(it.link)+'" target="_blank" rel="noopener noreferrer">'+esc(tn&&tn.title_cn?tn.title_cn:it.title)+'</a></div>';
  if(ctName)html+='<span class="type-tag type-'+esc(it.content_type)+'">'+ctName+'</span>';
  if(isGitHub)html+='<span class="github-badge">来源 GitHub</span>';
  if(imp==="S")html+='<span class="imp-badge imp-s-badge">S级</span>';
  if(imp==="A")html+='<span class="imp-badge imp-a-badge">推荐</span>';
  if(imp==="S"||imp==="A")html+='<span class="imp-sep"></span>';
  if(catName&&it.category!=="Other"&&it.category!=="General"){
    html+='<span class="cat-tag">'+esc(catName)+'</span>';
  }
  html+='<div class="imp-text">重要性: <strong>'+imp+'</strong> 评分: <strong>'+(it.value_score||0)+'</strong></div>';
  if(isGitHub){
    html+='<div class="github-stats">';
    html+='<span class="gh-stat"><span class="gh-stat-label">Stars</span><strong>'+esc(it.stars!=null?it.stars:"--")+'</strong></span>';
    html+='<span class="gh-stat"><span class="gh-stat-label">Forks</span><strong>'+esc(it.forks!=null?it.forks:"--")+'</strong></span>';
    html+='<span class="gh-stat"><span class="gh-stat-label">Score</span><strong>'+esc(it.github_score!=null?it.github_score:"--")+'</strong></span>';
    html+='</div>';
  }
  if(it.tags&&it.tags.length>0){
    html+='<div class="news-tags">';
    for(var j=0;j<it.tags.length;j++){
      html+='<span class="tag tag-'+it.tags[j].t+'">'+esc(it.tags[j].l)+'</span>';
    }
    html+='</div>';
  }
  if(tn&&tn.summary_cn){html+='<div class="news-chinese-summary">'+esc(tn.summary_cn.slice(0,200))+'</div>';}else if(it.chinese_summary){
    html+='<div class="news-chinese-summary">'+esc(it.chinese_summary.slice(0,200))+'</div>';
  }
  html+='<div class="news-footer">';
  html+='<span class="news-source">'+esc(it.source)+'</span>';
  html+='<span class="news-time">'+esc(it.published_ago||"")+'</span>';
  html+='<div class="hotness-bar-wrap">';
  html+='<span class="hotness-label">'+it.hotness+'</span>';
  html+='<div class="hotness-track"><div class="hotness-fill '+hc+'" style="width:'+it.hotness+'%"></div></div>';
  html+='</div></div></div></div>';
  return html;
}

function renderItems(items){
  var html="",count=items.length;
  var hasFilter=categoryFilter!=="all"||importanceFilter!=="all"||contentTypeFilter!=="all"||eventTypeFilter!=="all"||searchQuery;
  if(items.length===0){
    var msg=hasFilter?"没有匹配的文章":"暂无数据";
    newsList.innerHTML='<div class="empty-state"><h3>'+msg+'</h3></div>';
    newsCount.textContent=count+"/"+allItems.length+" 条";
    return;
  }
  var totalStr=hasFilter?count+"/"+allItems.length+" 条":"共 "+count+" 条";
  newsCount.textContent=totalStr;
  html=items.map(renderNewsCard).join("");
  newsList.innerHTML=html;
}

function loadNews(cat,showLoading){
  if(showLoading){newsList.innerHTML='<div class="loading-spinner">加载中...</div>';}
  setStatus("loading");
  fetch("/api/news?category="+cat+"&_="+Date.now())
  .then(function(r){
    if(!r.ok)throw new Error("HTTP "+r.status);
    return r.json();
  })
  .then(function(data){
    allItems=sortItems(data.items||[]);
    buildFilters();
    newsCount.textContent="共 "+allItems.length+" 条";
    newsUpdated.textContent=data.updated_at?"更新于 "+timeAgo(data.updated_at):"";
    renderWithFilter();
    setStatus("ready");
  })
  .catch(function(err){
    console.error("loadNews:",err);
    newsList.innerHTML='<div class="empty-state"><h3>加载失败</h3><p>'+esc(err.message||"请求异常")+'</p></div>';
    setStatus("error");
  });
}

function loadGamingHotspots(cat){
  var sec=document.getElementById("gamingHotspotSection");
  if(!sec)return;
  if(cat!=="gaming"){gamingHotspots=[];sec.innerHTML="";return;}
  sec.innerHTML='<div class="hotspot-loading">加载运营热点中...</div>';
  fetch("/api/gaming/hotspots?_="+Date.now())
  .then(function(r){if(!r.ok)throw Error("HTTP "+r.status);return r.json();})
  .then(function(d){
    gamingHotspots=d.items||[];
    renderGamingHotspots(filterGamingHotspots());
  })
  .catch(function(e){
    console.error("gaming hotspots:",e);
    sec.innerHTML="";
  });
}

function pickBestSource(sources){
  var list=sources||[];
  if(!list.length)return null;
  var best=list[0],bestP=-1;
  for(var i=0;i<list.length;i++){
    var s=list[i];
    var p=typeof s==="object"&&s!==null?(Number(s.priority)||0):0;
    if(p>bestP){best=s;bestP=p;}
  }
  return best;
}

function renderGamingHotspots(items){
  var sec=document.getElementById("gamingHotspotSection");
  if(!sec)return;
  if(!items.length){sec.innerHTML="";return;}
  var html='<div class="hotspot-header"><span class="hotspot-title-label">运营热点</span><span class="hotspot-total">'+items.length+' 条</span></div>';
  html+='<div class="gaming-hotspot-list">';
  for(var i=0;i<items.length;i++){
    var it=items[i];
    var ev=GAMING_EVENT_CN[it.event_type]||EVENT_CN[it.event_type]||it.event_type||"";
    var imp=it.importance||"";
    var best=pickBestSource(it.recommended_sources);
    var srcName=best?(typeof best==="string"?best:(best.source_name||best.name||best.title||"")):"";
    var srcUrl=best?(typeof best==="string"?best:(best.url||best.link||"")):"";
    html+='<div class="gaming-hotspot-card">';
    html+='<div class="gaming-hotspot-name">'+esc(it.game_name||"未知游戏")+'</div>';
    html+='<div class="gaming-hotspot-meta">';
    if(ev)html+='<span class="gaming-hotspot-event">'+esc(ev)+'</span>';
    if(imp)html+='<span class="gaming-hotspot-imp">'+esc(imp)+' 级</span>';
    html+='<span class="gaming-hotspot-score">热度 '+(it.hotspot_score!=null?it.hotspot_score:"--")+'</span>';
    html+='</div>';
    if(srcName&&srcUrl){
      html+='<div class="gaming-hotspot-sources"><span class="gaming-source-name">'+esc(srcName)+'</span>';
      html+='<a class="gaming-source-btn" href="'+esc(srcUrl)+'" target="_blank" rel="noopener noreferrer">查看官方来源</a></div>';
    }
    html+='</div>';
  }
  html+='</div>';
  sec.innerHTML=html;
}

function switchTab(cat){
  currentCat=cat;
  importanceFilter="all";categoryFilter="all";contentTypeFilter="all";eventTypeFilter="all";searchQuery="";
  if(searchTimer){clearTimeout(searchTimer);}
  if(searchInput){searchInput.value="";}
  if(searchClear){searchClear.classList.remove("visible");}
  for(var i=0;i<tabs.length;i++){
    tabs[i].classList.toggle("active",tabs[i].dataset.category===cat);
  }
  loadNews(cat,true);
  loadGamingHotspots(cat);
}

function refresh(){
  if(isRefreshing)return;
  isRefreshing=true;
  btnRefresh.classList.add("spinning");
  setStatus("loading");
  fetch("/api/refresh",{method:"POST"})
  .then(function(r){if(!r.ok)throw new Error("HTTP "+r.status);return r.json();})
  .then(function(){loadNews(currentCat,false);})
  .catch(function(err){console.error(err);setStatus("error");})
  .then(function(){isRefreshing=false;btnRefresh.classList.remove("spinning");});
}

document.getElementById("filterBar").addEventListener("click",function(e){
  var btn=e.target;
  if(!btn.classList.contains("fb-btn"))return;
  var f=btn.dataset.f, v=btn.dataset.v;
  if(f==="imp"){importanceFilter=v;}
  else if(f==="cat"){categoryFilter=v;}
  else if(f==="type"){if(v!==contentTypeFilter){contentTypeFilter=v;categoryFilter="all";}}
  else if(f==="event"){eventTypeFilter=v;}
  buildFilters();
  renderWithFilter();
});

for(var i=0;i<tabs.length;i++){
  tabs[i].addEventListener("click",function(){switchTab(this.dataset.category);});
}

dateDisplay.textContent=(function(now){
  var y=now.getFullYear(),m=String(now.getMonth()+1).padStart(2,"0"),d=String(now.getDate()).padStart(2,"0");
  return y+"年"+m+"月"+d+"日 星期"+["日","一","二","三","四","五","六"][now.getDay()];
})(new Date());

function loadTranslations(){fetch("/api/translations?_="+Date.now()).then(function(r){if(!r.ok)throw Error("HTTP "+r.status);return r.json();}).then(function(d){translations=d||{};if(allItems.length){allItems=sortItems(allItems);renderWithFilter();}}).catch(function(e){console.error("translations:",e);});}
loadTranslations();
loadGamingHotspots("ai");
loadNews("ai",true);
btnRefresh.addEventListener("click",refresh);
if(searchInput&&searchClear){
  var searchTimer=null;
  searchInput.addEventListener("input",function(){
    clearTimeout(searchTimer);
    searchTimer=setTimeout(function(){
      searchQuery=searchInput.value;
      searchClear.classList.toggle("visible",searchQuery.length>0);
      renderWithFilter();
    },150);
  });
  searchClear.addEventListener("click",function(){
    searchInput.value="";
    searchQuery="";
    searchClear.classList.remove("visible");
    renderWithFilter();
    searchInput.focus();
  });
}
setInterval(function(){loadNews(currentCat,false);},300000);
})();
