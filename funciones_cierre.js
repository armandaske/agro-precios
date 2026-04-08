// JavaScript Document
var noseg='';
function llenaCombos(){
	//alert('Hola');
	startLoad();
	xajax_llenaAnios();
	xajax_llenaCiclo();
	xajax_llenaModa();
	xajax_llenaEntidades();
	xajax_llenaTipoAgric(0);
	xajax_llenaTipoProd(0);
	xajax_llenaTipoMerc(0);
	//xajax_llenaCultivo('G',$('#anioagric').val());
}

function llenaCultivo(){
	xajax_llenaCultivo($('#anioagric').val(),$('#entidad').val(),'');
}

function llenaDisMun(){
	startLoad();
	xajax_llenaDistrito($('#entidad').val());
	xajax_cargaMuni($('#entidad').val(),0);
	llenaCultivo();
	xajax_llenaUnidMed(0);
	llenaVariedad();
}

function llenaMuni(){
	startLoad();
	//alert($('#entidad').val()+' - '+$('#distrito').val());
	if($('.muniSel').css('display') == 'none'){
		//alert(0);
		xajax_cargaMuni($('#entidad').val(),0);
	}else{
		//alert(1);
		xajax_cargaMuni($('#entidad').val(),$('#distrito').val());
	}
}

function llenaUnidMed(){
	startLoad();
	xajax_llenaUnidMed($('#cultivo').val());
}

function llenaVariedad(){
	startLoad();
	xajax_llenaVariedad($('#cultivo').val(),$('#unidMed').val());
}

function reporte(){
	//alert($('#tipo-reporte').val());
	startLoad();
	var tipo = $('#tipo-reporte').val();
	var anioagric = $('#anioagric').val();
	var cicloProd = $('#cicloProd').val();
	var modalidad = $('#modalidad').val();
	var entidad = $('#entidad').val();
	var distrito = $('#distrito').val();
	var municipio = $('#municipio').val();
	var cultivo = $('#cultivo').val();
	var unidMed = $('#unidMed').val();
	var variedad = $('#variedad').val();
	var opcionDDRMpio = $('input:radio[name=opcionDDRMpio]:checked').val();
	
	var agric = $('#agric').val();
	var tiprod = $('#tiprod').val();
	var timerc = $('#timerc').val();
	
	/*alert("Tipo: " + tipo +
	"\nAño Agrícola: " + anioagric +
	"\nCiclo: " + cicloProd +
	"\nModalidad: " + modalidad + 
	"\nEntidad: " + entidad +
	"\nDistrito: " + distrito + 
	"\nMunicipio: " + municipio +
	"\nCultivo: " + cultivo +
	"\nUnidad de Medida: " + unidMed +
	"\nVariedad: " + variedad +
	"\nTipo DDR Mpio: " + opcionDDRMpio);*/
	
	xajax_reporte(tipo , anioagric , cicloProd , modalidad , entidad , distrito , municipio ,cultivo , unidMed , variedad , opcionDDRMpio,agric,tiprod,timerc,noseg);
}

function selecTipo(tipo){
//	alert(tipo);
	//xajax_cargamunicipio(null);
	//xajax_cargamuni(null,null);
	if(tipo==1){
		$("#tipo-edo").css({'background-color': '#CCC'});
		$("#tipo-cult").removeAttr( 'style' );
		$("#tipo-cult-var").removeAttr( 'style' );
		$("#tipo-reporte").val('1');
		$('.div-estado-distmun').show();
		$('.div-mun').show();
		//$('.divCultivo').show();
		//$('#cveEstado > option[value="0"]').attr('selected', 'selected');
		//$('.div-mun-select').hide();
		//$('.div-muni-select').hide();
	}else if(tipo==2){
		$(".div-tipovari").hide();
		//xajax_llenaVariedad(null);
		$('#cveCultivo > option[value="0"]').attr('selected', 'selected');
		$("#tipo-cult").css({'background-color': '#CCC'});
		$("#tipo-edo").removeAttr( 'style' );
		$("#tipo-cult-var").removeAttr( 'style' );
		$("#tipo-reporte").val('2');
		$('.div-estado-distmun').hide();
		$('.div-mun').hide();
		//$('.divCultivo').hide();
		//$('.div-mun-select').show();
		//$('.div-muni-select').show();
		//$('#cveEstado > option[value="0"]').attr('selected', 'selected');
	}else if(tipo==3){
		$(".div-tipovari").hide();
		//xajax_llenaVariedad(null);
		$('#cveCultivo > option[value="0"]').attr('selected', 'selected');
		$("#tipo-cult-var").css({'background-color': '#CCC'});
		$("#tipo-edo").removeAttr( 'style' );
		$("#tipo-cult").removeAttr( 'style' );
		$("#tipo-reporte").val('3');
		$('.div-estado-distmun').hide();
		$('.div-mun').hide();
		/*$('.divCultivo').hide();
		$('.div-mun-select').show();
		$('.div-muni-select').show();
		$('#cveEstado > option[value="0"]').attr('selected', 'selected');*/
	}
	stopLoad();	
	
	//alert($("#tipo-reporte").val());
}

function printDiv(nombreDiv) {
     var contenido= document.getElementById(nombreDiv).innerHTML;
     var contenidoOriginal= document.body.innerHTML;

     document.body.innerHTML = contenido;

     window.print();

     document.body.innerHTML = contenidoOriginal;
}

function descargarExcel(){
	window.location.href = "Clases/reporte.php";
}

function verSels(tipo){
//	alert(tipo);
	if(tipo === 1){
		$("#opcionDDRMpio1").prop("checked", true);
		$('.distSel').hide();
		$('.muniSel').hide();
		document.getElementById("distrito").selectedIndex=0;
		document.getElementById("municipio").selectedIndex=0;
	}else if(tipo === 2){
		$('.distSel').show();
		$('.muniSel').show();
		document.getElementById("distrito").selectedIndex=0;
		document.getElementById("municipio").selectedIndex=0;
	}else if(tipo === 3){
		$('.distSel').show();
		$('.muniSel').hide();
		document.getElementById("distrito").selectedIndex=0;
		document.getElementById("municipio").selectedIndex=0;
	}else if(tipo === 4){
		$('.distSel').hide();
		$('.muniSel').show();
		document.getElementById("distrito").selectedIndex=0;
		document.getElementById("municipio").selectedIndex=0;
	}else if(tipo === 5){
		$('.distSel').show();
		$('.muniSel').show();
		document.getElementById("distrito").selectedIndex=0;
		document.getElementById("municipio").selectedIndex=0;
	}
}

function verNoSeguimiento(ver){
	//alert("ver: "+ver);
	if(ver === 1){
		$('.idnoseguimiento').show();
		$('#seguimientoC').show();
		$('.idseguimiento').hide();
		$("#seguimientoC").html("Cultivos de seguimiento");
		
	}else if(ver === 2){
		$('.idnoseguimiento').hide();
		$('#seguimientoC').show();
		$('.idseguimiento').show();
		$("#seguimientoC").html("Cultivos de seguimiento");
		noseg='';
	}else if(ver === 3){
		//$(".idnoseguimiento").css({'background-color': '#090'});
		$('.idseguimiento').show();
		$('.idnoseguimiento').hide();
		$('#seguimientoC').show();
		$("#seguimientoC").html("Todos los cultivos");
		noseg='_ns';
		
		// Ocultar los no requeridos:
		
		$("#opcionDDRMpio1").attr('checked', true);
		verSels(1);
		$('.idporcheck').hide();
		$('.ocultaNS').hide();
		
		document.getElementById("variedad").selectedIndex=0;
		document.getElementById("agric").selectedIndex=0;
		document.getElementById("timerc").selectedIndex=0;
		document.getElementById("tiprod").selectedIndex=0;
		
		xajax_llenaCultivo($('#anioagric').val(),$('#entidad').val(),'_ns');
		
	}else if(ver === 4){
		//$(".idnoseguimiento").css({'background-color': '#090'});
		$('#seguimientoC').show();
		$('.idseguimiento').hide();
		$('.idnoseguimiento').show();
		$("#seguimientoC").html("Cultivos de seguimiento");
		noseg='';
		
		//Mostrar los requeridos:
		$('.idporcheck').show();
		$('.ocultaNS').show();
		xajax_llenaCultivo($('#anioagric').val(),$('#entidad').val(),'');
		
	}else if(ver === 5){
		//$(".idnoseguimiento").css({'background-color': '#090'});
		$('.idseguimiento').hide();
		$('.idnoseguimiento').hide();
		$('#seguimientoC').hide();
		$('.idporcheck').show();
		$('.ocultaNS').show();
		//xajax_llenaCultivo($('#anioagric').val(),$('#entidad').val(),'');
		noseg='';
		
	}
}







