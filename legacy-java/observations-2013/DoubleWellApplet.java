//=====================================================================
// File: DoubleWellApplet.java
//
// Applied Math 303, Term Project
// Blair Fraser, 2303725
//=====================================================================
import java.applet.Applet;
import java.awt.*;
import java.lang.*;
import java.io.*;
import java.net.*;
import java.util.Scanner;
public class DoubleWellApplet extends Applet implements Runnable {  
  //=====================================================================
  // Variables
  //
  //=====================================================================
  DoubleWellCanvas equationCanvas;
  Thread thread;
  Button stopStart;
  TextField monthText, InitialMonthText, yearText, forceAmpText2, 
            FinalMonthText, finaltText; 			
  String fileToRead = "test1.txt";	
  StringBuffer strBuff;
  TextArea MinhaArea;		
  String STempe;
  String SdTdt;
  String SAno;
  String SMes;
  String SPonto;
  //int[][] a = new int[2][4];  // Two rows and four columns.
  double[] ITempe = new double[10000];
  double[] IdTdt  = new double[10000];
  int[] IAno   = new int[10000];
  int[] IMes   = new int[10000];
  int[] IPonto = new int[10000];
  double stepSize1;

  //=====================================================================
  // Methods
  //
  //=====================================================================
  //=====================================================================
  // initialize
  //
  // Initialize the applet, create the user interface, get parameters 
  // from the html file, create the equation canvas.
  //=====================================================================
  public void init() {
	//setLayout(new BorderLayout());   //Era assim originalmente. (N/S/E/W/Center)
	setLayout(new FlowLayout());       //Mudei para isso para poder fazer funcionar o readFileApplet
    //----------------
    // Get parameters
    //----------------
    String str = new String();
	
    str = getParameter("initial_position");
    double mes = Double.valueOf(str).doubleValue();

    str = getParameter("strange_month");
    double StrangeMonth = Double.valueOf(str).doubleValue();

    str = getParameter("Initial_Month");
    double InitialMonth = Double.valueOf(str).doubleValue();

    str = getParameter("initial_year");
    double initialyear = Double.valueOf(str).doubleValue();
    double initialt = (initialyear - 1950.0)*12.*5. + (InitialMonth - 1.0)*5.;

    str = getParameter("Final_Month");
    double FinalMonth = Double.valueOf(str).doubleValue();  

    str = getParameter("final_year");
    double finalyear = Double.valueOf(str).doubleValue();
    double finalt = (finalyear - 1950.0)*12.*5. + (FinalMonth - 0.0)*5.;

    str = getParameter("time_step");
    double stepSize = Double.valueOf(str).doubleValue();
	stepSize1 = 1.0;
	//stepSize1 = 0.05;

    str = getParameter("interface_on");
    boolean buttonsOn = Boolean.valueOf(str).booleanValue(); 

    str = getParameter("maximum_x");
    double domainMaxx = Double.valueOf(str).doubleValue();

    str = getParameter("minimum_x");
    double domainMinx = Double.valueOf(str).doubleValue();

    str = getParameter("maximum_y");
    double domainMaxy = Double.valueOf(str).doubleValue();

    str = getParameter("minimum_y");
    double domainMiny = Double.valueOf(str).doubleValue();   
    //----------------------------
    // Create the equation canvas
    //----------------------------
    equationCanvas = new DoubleWellCanvas();
    equationCanvas.setParams( 0.0, StrangeMonth, 0.0, 0.0);
    equationCanvas.setInitialState( initialt, 0.0, 0.0, finalt);
    equationCanvas.setDomain(domainMaxx,domainMinx,domainMaxy,domainMiny);
    equationCanvas.setTimeStep(stepSize);
	//------------------------------
	//  To tentando...
    equationCanvas.PassaDados(stepSize1,ITempe,IdTdt);
	
    //-----------------------------
    // Create buttons if nessasary 
    //-----------------------------  
    if(buttonsOn) {
      //-------------------------
      // Parameter 1 = Month
      //-------------------------
      Panel param1Panel = new Panel();
      param1Panel.setLayout(new BorderLayout());
      param1Panel.add("West", new Label("Month"));
      monthText = new TextField(StrangeMonth+"", 8);
      param1Panel.add("East", monthText);
	  	  
      /*
	  //-------------------------
      // Parameter 1_1 = Minha Área
      //-------------------------	  
	  
	  Panel param1_1Panel = new Panel();
	  param1_1Panel.setLayout(new BorderLayout());
	  param1_1Panel.add("West", new Label("DATA"));
	  */

      //-------------------------
      // Parameter 2 = Initial Month
      //-------------------------
      Panel param2Panel = new Panel();
      param2Panel.setLayout(new BorderLayout());
      param2Panel.add("West", new Label("Initial Month"));
      InitialMonthText = new TextField(InitialMonth+"", 8);
      param2Panel.add("East", InitialMonthText);

      //----------------
      // Panel Number 1
      //----------------
      Panel panelNo1 = new Panel();
      panelNo1.setLayout(new BorderLayout());
      panelNo1.add("North", param1Panel);
      ////panelNo1.add("South", param1_1Panel);

      //---------------------------------
      // Parameter 3 = initial year
      //---------------------------------
      Panel param3Panel = new Panel();
      param3Panel.setLayout(new BorderLayout());
      param3Panel.add("West", new Label("Initial Year"));
      yearText = new TextField(initialyear+"", 8);
      param3Panel.add("East", yearText);

      //---------------------------------
      // Parameter 4 = forcing frequency
      // Parameter 4 = Final Month
      //---------------------------------
      Panel param4Panel = new Panel();
      param4Panel.setLayout(new BorderLayout());
 //   param4Panel.add("West", new Label("forcing frequency"));
	  param4Panel.add("West", new Label("Final Month"));

//    forceFreqText = new TextField(forcingFreq+"", 8);
	  FinalMonthText = new TextField(FinalMonth+"", 8);
//    param4Panel.add("East", forceFreqText);
      param4Panel.add("East", FinalMonthText);
      
      //----------------
      // Panel Number 2
      //----------------
      Panel panelNo2 = new Panel();
      panelNo2.setLayout(new BorderLayout());
      panelNo2.add("North", param3Panel);
      panelNo2.add("South", param2Panel);

      //----------------------------------
      // Parameter 5 = Final Year
      //----------------------------------
      Panel param5Panel = new Panel();
      param5Panel.setLayout(new BorderLayout());
      param5Panel.add("West", new Label("Final Year"));
      finaltText = new TextField(finalyear+"", 8);
      param5Panel.add("East", finaltText);

      //---------------------------------
      // Parameter 6 = forcing amplitude2
      //---------------------------------
 //   Panel param6Panel = new Panel();
 //   param6Panel.setLayout(new BorderLayout());
 //   param6Panel.add("West", new Label("forcing amplitude2"));
 //   forceAmpText2 = new TextField(forcingAmp2+"", 8);
 //   param6Panel.add("East", forceAmpText2);

      //----------------
      // Panel Number 3
      //----------------
      Panel panelNo3 = new Panel();
      panelNo3.setLayout(new BorderLayout());
      panelNo3.add("North", param5Panel);
      panelNo3.add("South", param4Panel);

      //-----------------------------------
      // Input bar panel, user text boxes.
      //-----------------------------------
      Panel inputBar = new Panel();
      inputBar.setLayout(new FlowLayout());
      inputBar.add(panelNo1);
      inputBar.add(panelNo2);
      inputBar.add(panelNo3);

      //-------------------------------------------
      // Control Bar Panel, entire user interface.
      //-------------------------------------------
      Panel controlBar = new Panel();
      controlBar.setLayout(new BorderLayout());
      stopStart = new Button("Clique aqui para reiniciar com novos dados.");
      controlBar.add("North", stopStart);
      controlBar.add("South", inputBar);

      add("South", controlBar);

    } else {
      //-------------------------------------------------
      // If interface is off, just add a restart button.
      //-------------------------------------------------
      add("South", new Button("Restart"));
    }//if(buttonsOn)
    add("Center",equationCanvas);
    show();	
	MinhaArea = new TextArea(3, 50);
	MinhaArea.setEditable(true);
	add(MinhaArea, "center");
	String prHtml = this.getParameter("fileToRead");
	if (prHtml != null) fileToRead = new String(prHtml);
	MinhaArea.append("Observações: \n");
	readFile();	
  }//public void init()
  //=====================================================================
  // start
  //
  // Start the thread.
  //=====================================================================
  public void start() {
    thread = new Thread(this);
    thread.start();
  }
  //=====================================================================
  // stop
  //
  // Stop the thread.
  //=====================================================================
  public void stop() {
    if(thread != null) {
      thread.stop();
      thread = null;
    }
  }
  //=====================================================================
  // run
  //
  // Run the thread, this is the main loop of the applet.
  //=====================================================================
  public void run() {
    while(true) {
      try {
        thread.sleep(25);
      }catch(InterruptedException e) {
        break;
      }
      equationCanvas.increment();
      equationCanvas.repaint();
    }
  }
  
  //=====================================================================
  // handle action
  //
  // How to handle a button click.
  //=====================================================================
  public boolean action(Event evt, Object arg) {
    if(evt.target instanceof Button) {
      if(arg.equals("Clique aqui para reiniciar com novos dados.")) {
        double StrangeMonth = Double.valueOf(monthText.getText()).doubleValue();
        double inityear = Double.valueOf(yearText.getText()).doubleValue();
        double initmes = Double.valueOf(InitialMonthText.getText()).doubleValue();
        double initt = (inityear - 1950.0)*12.*5. + (initmes - 1.0)*5.;
        double endyear = Double.valueOf(finaltText.getText()).doubleValue();
        double endmes = Double.valueOf(FinalMonthText.getText()).doubleValue();
        double endt = (endyear - 1950.0)*12.*5. + (endmes - 0.0)*5.;
        equationCanvas.setParams(endt, StrangeMonth, 0.0, 0.0);
		double stepSize = 1.0;
		equationCanvas.setTimeStep(stepSize);
		equationCanvas.PassaDados(stepSize1,ITempe,IdTdt);
        double initx = 999;
        double inity = 0.0;
        equationCanvas.setInitialState(initt , initx, inity, endt);
        equationCanvas.restart();
      } else if(arg.equals("Restart")) {
        equationCanvas.restart();
      }
      return(true);
    }
    return(false);
  }//public boolean action(Event evt, Object arg)
  public void readFile(){
	String line;
	int icont = -1;
	URL url = null;
	try{
	  url = new URL(getCodeBase(), fileToRead);
	}
    catch(MalformedURLException e){}
    try{
	  InputStream in = url.openStream();
	  BufferedReader bf = new BufferedReader(new InputStreamReader(in));
	  strBuff = new StringBuffer();
	  while((line = bf.readLine()) != null){	  
	    icont = icont + 1;
	    strBuff.append(line + "  XX\n");
		processLine(line);
		
		ITempe[icont] = (Double.valueOf(STempe.trim()).doubleValue()-22.0)*100.0;
		IdTdt[icont]  = (Double.valueOf(SdTdt.trim()).doubleValue())*100.0;
		IAno[icont]   = Integer.valueOf(SAno.trim()).intValue();
		IMes[icont]   = Integer.valueOf(SMes.trim()).intValue();
		IPonto[icont] = Integer.valueOf(SPonto.trim()).intValue();
		/*
		MinhaArea.append("São dados = ("+
		                  Integer.toString(icont)+") "+
		                  Double.toString(ITempe[icont])+"; "+
						  Double.toString(IdTdt[icont])+"; "+
						  Integer.toString(IAno[icont])+"; "+
						  Integer.toString(IMes[icont])+"; "+
						  Integer.toString(IPonto[icont])+"; "+					  
						  "\n");
		*/
      }
      double a = 22.00;
      String aString = Double.toString(a);
      String MeuString = "A 1ª coluna é a temperatura. \n A 2ª coluna é a taxa de variação mensal da temperatura.";

      MinhaArea.append("A Temperatura da referência central do gráfico é  = " + aString + "\n\n");
      MinhaArea.append("Notas: " + MeuString + "\n\n");
      MinhaArea.append("O arquivo de nome: " + fileToRead + ", segue abaixo:" + "\n\n");
      MinhaArea.append(strBuff.toString());
	}//try
	catch(IOException e){
	  e.printStackTrace();
	}
  }//public void readFile()
  protected void processLine(String aLine){
    //public void processLine(String aLine){
    //http://www.javapractices.com/topic/TopicAction.do?Id=87
    //use a second Scanner to parse the content of each line 
    Scanner scanner = new Scanner(aLine);
    scanner.useDelimiter(";");
    if ( scanner.hasNext() ){
	//  Temperatura = "Porra de Temperatura!";
	    STempe = scanner.next();
        SdTdt = scanner.next();
	    SAno = scanner.next();
	    SMes = scanner.next();
	    SPonto = scanner.next();
    }	
	scanner.close();
  }//protected void processLine(String aLine)
}//public class DoubleWellApplet extends Applet implements Runnable
