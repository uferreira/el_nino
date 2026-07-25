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

// public class DoubleWellApplet extends Applet implements Runnable {
import java.applet.Applet;

public class DoubleWellApplet extends Applet implements Runnable {

  
  //=====================================================================
  // Variables
  //
  //=====================================================================
  DoubleWellCanvas equationCanvas;
  Thread thread;
  Button botaoReiniciar, botaoPausar;
  TextField positionText, velocityText, 
            forceFreqText,forceAmplText , forceFaseText , 
            forceAmpl2Text ,forceFase2Text , dampenText, 
            apartingText, restoringText,
            initialMonthText, coefK2Text, 
            coefK0Text, coefK4Text, 
            coefK5Text, stepSizeText,
            strangeMonthText, domainMaxxText,
            domainMintText, domainMaxtText;
double domainMaxx, domainMinx, domainMiny, domainMaxy,domainMaxt, domainMint;

String fileToRead = "test1.txt";
StringBuffer strBuff;
TextArea txtArea;
boolean porradobotao;

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
    

    //setLayout(new BorderLayout());   //Era assim originalmente.
	setLayout(new FlowLayout());       //Mudei para isso para poder fazer funcionar o readFileApplet


	porradobotao = false;

    //----------------
    // Get parameters
    //----------------
    String str = new String();

    str = getParameter("initial_position");
    double initialx = Double.valueOf(str).doubleValue();

    str = getParameter("initial_velocity");
    double initialy = Double.valueOf(str).doubleValue();

    str = getParameter("forcing_amplitude");
    double forcingAmpl  = Double.valueOf(str).doubleValue();

    str = getParameter("forcing_fase");
    double forcingFase = Double.valueOf(str).doubleValue();

    str = getParameter("aparting_k1");
    double apartingK1 = Double.valueOf(str).doubleValue();

    str = getParameter("restoring_k3");
    double restoringK3 = Double.valueOf(str).doubleValue();

    str = getParameter("forcing_amplitude2");
    double forcingAmpl2 = Double.valueOf(str).doubleValue();

    str = getParameter("forcing_fase2");
    double forcingFase2 = Double.valueOf(str).doubleValue();

    str = getParameter("dampening_constant");
    double dampening = Double.valueOf(str).doubleValue();

    str = getParameter("forcing_frequency");
    double forcingFreq = Double.valueOf(str).doubleValue();    

    str = getParameter("initial_month");
    double initialMonth = Double.valueOf(str).doubleValue();

    str = getParameter("coef_K2");
    double coefK2 = Double.valueOf(str).doubleValue();

    str = getParameter("coef_K0");
    double coefK0 = Double.valueOf(str).doubleValue();

    str = getParameter("coef_K4");
    double coefK4 = Double.valueOf(str).doubleValue();

    str = getParameter("coef_K5");
    double coefK5 = Double.valueOf(str).doubleValue();

    str = getParameter("time_step");
    double stepSize = Double.valueOf(str).doubleValue();

    str = getParameter("strange_month");
    double strangeMonth = Double.valueOf(str).doubleValue();    

    str = getParameter("maximum_x");
    domainMaxx = Double.valueOf(str).doubleValue();

    str = getParameter("minimum_t");
    double domainMint = Double.valueOf(str).doubleValue();
 
    str = getParameter("maximum_t");
    double domainMaxt = Double.valueOf(str).doubleValue(); 

    str = getParameter("interface_on");
    boolean buttonsOn = Boolean.valueOf(str).booleanValue(); 


//    str = getParameter("minimum_x");
//    domainMinx = Double.valueOf(str).doubleValue();

//    str = getParameter("minimum_y");
//    domainMiny = Double.valueOf(str).doubleValue();   

//    str = getParameter("maximum_y");
//    domainMaxy = Double.valueOf(str).doubleValue();


    //----------------------------
    // Create the equation canvas
    //----------------------------
    equationCanvas = new DoubleWellCanvas();
    equationCanvas.setParams(dampening, apartingK1, restoringK3, forcingAmpl , forcingFase, forcingAmpl2, forcingFase2, forcingFreq, coefK0, coefK2, coefK4, coefK5,stepSize);

    equationCanvas.setInitialState(initialMonth - 0.5, initialx, initialy, 0.0);

    double domainMinx = -domainMaxx;
    double domainMaxy = domainMaxx/2.;
    double domainMiny = -domainMaxx/2.;

    equationCanvas.setDomain(domainMaxx,domainMinx,domainMaxy,domainMiny,strangeMonth,domainMaxt,domainMint);
    equationCanvas.setTimeStep(stepSize);

    //-----------------------------
    // Create buttons if nessasary 
    //-----------------------------  
    if(buttonsOn) {

      //-------------------------
      // Parameter 1 = initial x
      //-------------------------
      Panel param1Panel = new Panel();
      param1Panel.setLayout(new BorderLayout());
      param1Panel.add("West", new Label("X0"));
      positionText = new TextField(initialx+"", 8);
      param1Panel.add("East", positionText);

      //-------------------------
      // Parameter 2 = initial y
      //-------------------------
      Panel param2Panel = new Panel();
      param2Panel.setLayout(new BorderLayout());
      param2Panel.add("West", new Label("V0"));
      velocityText = new TextField(initialy+"", 8);
      param2Panel.add("East", velocityText);


      //----------------
      // Panel Number 1
      //----------------
      Panel panelNo1 = new Panel();
      panelNo1.setLayout(new BorderLayout());
      panelNo1.add("North", param1Panel);
      panelNo1.add("South", param2Panel);
 //////////////////////////////////////////////////////////////////////

      //---------------------------------
      // Parameter 3 = aparting K1
      //---------------------------------
      Panel param3Panel = new Panel();
      param3Panel.setLayout(new BorderLayout());
      param3Panel.add("West", new Label("K1"));
      apartingText = new TextField(apartingK1+"", 8);
      param3Panel.add("East", apartingText);


      //---------------------------------
      // Parameter 4 = restoring K3
      //---------------------------------
      Panel param4Panel = new Panel();
      param4Panel.setLayout(new BorderLayout());
      param4Panel.add("West", new Label("K3"));
      restoringText = new TextField(restoringK3+"", 8);
      param4Panel.add("East", restoringText);

 
      //----------------
      // Panel Number 2
      //----------------
      Panel panelNo2 = new Panel();
      panelNo2.setLayout(new BorderLayout());
      panelNo2.add("North", param3Panel);
      panelNo2.add("South", param4Panel);
 //////////////////////////////////////////////////////////////////////


      //---------------------------------
      // Parameter 5 = forcing cos amplitude
      //---------------------------------
      Panel param5Panel = new Panel();
      param5Panel.setLayout(new BorderLayout());
      param5Panel.add("West", new Label("FA"));
      forceAmplText  = new TextField(forcingAmpl +"", 8);
      param5Panel.add("East", forceAmplText );


      //-------------------------
      // Parameter 6 = forcing sin amplitude
      //-------------------------
      Panel param6Panel = new Panel();
      param6Panel.setLayout(new BorderLayout());
      param6Panel.add("West", new Label("FF"));
      forceFaseText  = new TextField(forcingFase+"", 8);
      param6Panel.add("East", forceFaseText );



      //----------------
      // Panel Number 3
      //----------------
      Panel panelNo3 = new Panel();
      panelNo3.setLayout(new BorderLayout());
      panelNo3.add("North", param5Panel);
      panelNo3.add("South", param6Panel);
 //////////////////////////////////////////////////////////////////////


      //---------------------------------
      // Parameter 7 = forcing cos2 amplitude
      //---------------------------------
      Panel param7Panel = new Panel();
      param7Panel.setLayout(new BorderLayout());
      param7Panel.add("West", new Label("FA2"));
      forceAmpl2Text  = new TextField(forcingAmpl2+"", 8);
      param7Panel.add("East", forceAmpl2Text );

      //---------------------------------
      // Parameter 8 = forcing sin2 amplitude
      //---------------------------------
      Panel param8Panel = new Panel();
      param8Panel.setLayout(new BorderLayout());
      param8Panel.add("West", new Label("FF2"));
      forceFase2Text  = new TextField(forcingFase2+"", 8);
      param8Panel.add("East", forceFase2Text );

      //----------------
      // Panel Number 4
      //----------------
      Panel panelNo4 = new Panel();
      panelNo4.setLayout(new BorderLayout());
      panelNo4.add("North", param7Panel);
      panelNo4.add("South", param8Panel);
 //////////////////////////////////////////////////////////////////////


      //----------------------------------
      // Parameter 9 = dampening constant
      //----------------------------------
      Panel param9Panel = new Panel();
      param9Panel.setLayout(new BorderLayout());
      param9Panel.add("West", new Label("B"));
      dampenText = new TextField(dampening+"", 8);
      param9Panel.add("East", dampenText);

      //---------------------------------
      // Parameter 10 = forcing frequency
      //---------------------------------
      Panel param10Panel = new Panel();
      param10Panel.setLayout(new BorderLayout());
      param10Panel.add("West", new Label("W"));
      forceFreqText = new TextField(forcingFreq+"", 8);
      param10Panel.add("East", forceFreqText);


      //----------------
      // Panel Number 5
      //----------------
      Panel panelNo5 = new Panel();
      panelNo5.setLayout(new BorderLayout());
      panelNo5.add("North", param9Panel);
      panelNo5.add("South", param10Panel);
 //////////////////////////////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////



      //-------------------------
      // Parameter 11 = Month
      //-------------------------
      Panel param11Panel = new Panel();
      param11Panel.setLayout(new BorderLayout());
      param11Panel.add("West", new Label("Mo"));
      initialMonthText = new TextField(initialMonth+"", 8);
      param11Panel.add("East", initialMonthText);

      //-------------------------
      // Parameter 12 = K2
      //-------------------------
      Panel param12Panel = new Panel();
      param12Panel.setLayout(new BorderLayout());
      param12Panel.add("West", new Label("K2"));
      coefK2Text = new TextField(coefK2+"", 8);
      param12Panel.add("East", coefK2Text);


      //----------------
      // Panel Number 6
      //----------------
      Panel panelNo6 = new Panel();
      panelNo6.setLayout(new BorderLayout());
      panelNo6.add("North", param11Panel);
      panelNo6.add("South", param12Panel);
 //////////////////////////////////////////////////////////////////////

      //---------------------------------
      // Parameter 13 = K0
      //---------------------------------
      Panel param13Panel = new Panel();
      param13Panel.setLayout(new BorderLayout());
      param13Panel.add("West", new Label("K0"));
      coefK0Text = new TextField(coefK0+"", 8);
      param13Panel.add("East", coefK0Text);


      //---------------------------------
      // Parameter 14 =  K4
      //---------------------------------
      Panel param14Panel = new Panel();
      param14Panel.setLayout(new BorderLayout());
      param14Panel.add("West", new Label("K4"));
      coefK4Text = new TextField(coefK4+"", 8);
      param14Panel.add("East", coefK4Text);

 
      //----------------
      // Panel Number 7
      //----------------
      Panel panelNo7 = new Panel();
      panelNo7.setLayout(new BorderLayout());
      panelNo7.add("North", param13Panel);
      panelNo7.add("South", param14Panel);
 //////////////////////////////////////////////////////////////////////


      //---------------------------------
      // Parameter 15 = K5
      //---------------------------------
      Panel param15Panel = new Panel();
      param15Panel.setLayout(new BorderLayout());
      param15Panel.add("West", new Label("K5"));
      coefK5Text = new TextField(coefK5+"", 8);
      param15Panel.add("East", coefK5Text);


      //-------------------------
      // Parameter 16 = P16  time_step
      //-------------------------
      Panel param16Panel = new Panel();
      param16Panel.setLayout(new BorderLayout());
      param16Panel.add("West", new Label("Stp"));
      stepSizeText = new TextField(stepSize+"", 8);
      param16Panel.add("East", stepSizeText);



      //----------------
      // Panel Number 8
      //----------------
      Panel panelNo8 = new Panel();
      panelNo8.setLayout(new BorderLayout());
      panelNo8.add("North", param15Panel);
      panelNo8.add("South", param16Panel);
 //////////////////////////////////////////////////////////////////////


      //-------------------------
      // Parameter 17 = P17  strangeMonth
      //-------------------------
      Panel param17Panel = new Panel();
      param17Panel.setLayout(new BorderLayout());
      param17Panel.add("West", new Label("SMo"));
      strangeMonthText = new TextField(strangeMonth+"", 8);
      param17Panel.add("East", strangeMonthText);

      //-------------------------
      // Parameter 18 = P18  Escale
      //-------------------------
      Panel param18Panel = new Panel();
      param18Panel.setLayout(new BorderLayout());
      param18Panel.add("West", new Label("MAX"));
      domainMaxxText = new TextField(domainMaxx+"", 8);
      param18Panel.add("East", domainMaxxText);

      //----------------
      // Panel Number 9
      //----------------
      Panel panelNo9 = new Panel();
      panelNo9.setLayout(new BorderLayout());
      panelNo9.add("North", param17Panel);
      panelNo9.add("South", param18Panel);
 //////////////////////////////////////////////////////////////////////


      //-------------------------
      // Parameter 19 = MINIMUM T
      //-------------------------
      Panel param19Panel = new Panel();
      param19Panel.setLayout(new BorderLayout());
      param19Panel.add("West", new Label("TI"));
      domainMintText = new TextField(domainMint+"", 8);
      param19Panel.add("East", domainMintText);

      //-------------------------
      // Parameter 20 = MAXIMUM T
      //-------------------------
      Panel param20Panel = new Panel();
      param20Panel.setLayout(new BorderLayout());
      param20Panel.add("West", new Label("TF"));
      domainMaxtText = new TextField(domainMaxt+"", 8);
      param20Panel.add("East", domainMaxtText);


      //----------------
      // Panel Number 10
      //----------------
      Panel panelNo10 = new Panel();
      panelNo10.setLayout(new BorderLayout());
      panelNo10.add("North", param19Panel);
      panelNo10.add("South", param20Panel);
 //////////////////////////////////////////////////////////////////////
 //////////////////////////////////////////////////////////////////////







      //-----------------------------------
      // Input bar panel, user text boxes.
      //-----------------------------------
      Panel inputBar = new Panel();
      inputBar.setLayout(new FlowLayout());
      inputBar.add(panelNo1);
      inputBar.add(panelNo2);
      inputBar.add(panelNo3);
      inputBar.add(panelNo4);
      inputBar.add(panelNo5);




      //-----------------------------------
      // Constants bar panel, user text boxes.
      //-----------------------------------
      Panel ConstBar = new Panel();
      ConstBar.setLayout(new FlowLayout());
      ConstBar.add(panelNo6);
      ConstBar.add(panelNo7);
      ConstBar.add(panelNo8);
      ConstBar.add(panelNo9);
      ConstBar.add(panelNo10);




      //-------------------------------------------
      // Control Bar Panel, entire user interface.
      //-------------------------------------------
      Panel controlBar = new Panel();
      controlBar.setLayout(new BorderLayout());
      botaoReiniciar = new Button("Reiniciar com novos parametros");
	  botaoPausar = new Button("Pausar");
      controlBar.add("North", botaoReiniciar);
	  controlBar.add("Center", botaoPausar);
      controlBar.add("South", inputBar);


      add("North", ConstBar);
      add("South", controlBar);
	  
	  

	  
	  
    } else {
      //-------------------------------------------------
      // If interface is off, just add a restart button.
      //-------------------------------------------------
      add("South", new Button("Restart"));
    }

    add("Center",equationCanvas).setVisible(true); // to show the component;
    //show();
	
	
	
		//txtArea = new TextArea(100, 100);
		txtArea = new TextArea(3, 50);
		txtArea.setEditable(true);
		add(txtArea, "center");
		String prHtml = this.getParameter("fileToRead");
		if (prHtml != null) fileToRead = new String(prHtml);
		txtArea.append("Posso escrever aqui: \n");
		readFile();
	
	
  }


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
  //public void stop() {
  //  if(thread != null) {
  //    thread.stop();
  //    thread = null;
  //  }
  //}

  public void stop() {
    if (thread != null) {
        thread.interrupt(); // Request the thread to stop

        try {
            thread.join(); // Wait for the thread to complete
        } catch (InterruptedException e) {
            // Handle the InterruptedException
        }

        thread = null;
    }
}


  //=====================================================================
  // run
  //
  // Run the thread, this is the main loop of the applet.
  //=====================================================================
  // int contador=0;
  // public void run() {
  //   while(true) {
  //     try {
  //       thread.sleep(25);
  //     }catch(InterruptedException e) {
  //       break;
  //     }
	//   if (porradobotao == false) {
  //       int meXX = equationCanvas.incrementA();
	//     contador++;
	//     txtArea.append("T; X: " + contador + " ; " + meXX + " \n");
  //       }
	// 	equationCanvas.repaint();
  //   }
  // }
  // public void paint(Graphics g) { 
  // g.drawString("Karaca!",20,100); 
  // repaint();
  // }
  int contador = 0;

  public void run() {
      while (true) {
          try {
              Thread.sleep(25); // Use Thread.sleep(25);
          } catch (InterruptedException e) {
              break;
          }
          if (!porradobotao) {
              int meXX = equationCanvas.incrementA();
              contador++;
              txtArea.append("T; X: " + contador + " ; " + meXX + " \n");
          }
          equationCanvas.repaint();
      }
  }
  
  public void paint(Graphics g) {
      g.drawString("Karaca!", 20, 100);
      repaint();
  }
  
  //=====================================================================
  // handle action
  //
  // How to handle a button click.
  //=====================================================================
  public boolean action(Event evt, Object arg) {
  
    if(evt.target instanceof Button) {

      if(arg.equals("Reiniciar com novos parametros")) {
        double initx = Double.valueOf(positionText.getText()).doubleValue();
        double inity = Double.valueOf(velocityText.getText()).doubleValue();

        double fAmpl = Double.valueOf(forceAmplText .getText()).doubleValue();
        double fFase = Double.valueOf(forceFaseText .getText()).doubleValue();
        double fAmpl2 = Double.valueOf(forceAmpl2Text .getText()).doubleValue();
        double fFase2 = Double.valueOf(forceFase2Text .getText()).doubleValue();
        double apartK1 = Double.valueOf(apartingText.getText()).doubleValue();
        double restoK3 = Double.valueOf(restoringText.getText()).doubleValue();
        double damp = Double.valueOf(dampenText.getText()).doubleValue();
        double fFreq = Double.valueOf(forceFreqText.getText()).doubleValue();

        double coeK0 = Double.valueOf(coefK0Text.getText()).doubleValue();
        double coeK2 = Double.valueOf(coefK2Text.getText()).doubleValue();
        double coeK4 = Double.valueOf(coefK4Text.getText()).doubleValue();
        double coeK5 = Double.valueOf(coefK5Text.getText()).doubleValue();
		double NewstepSize = Double.valueOf(stepSizeText.getText()).doubleValue();
        equationCanvas.setTimeStep(NewstepSize);


        equationCanvas.setParams(damp, apartK1, restoK3, fAmpl, fFase, fAmpl2, fFase2, fFreq, coeK0, coeK2, coeK4, coeK5, NewstepSize);

        double initialMo = Double.valueOf(initialMonthText.getText()).doubleValue();
        equationCanvas.setInitialState(initialMo - 0.5, initx, inity, 0.0);

 
        double strangeMo = Double.valueOf(strangeMonthText.getText()).doubleValue();

        double domMaxx = Double.valueOf(domainMaxxText.getText()).doubleValue();
        double domMinx = -domMaxx;
        double domMaxy = domMaxx/2.;
        double domMiny = -domMaxx/2.;
        double domMaxt = Double.valueOf(domainMaxtText.getText()).doubleValue();
        double domMint = Double.valueOf(domainMintText.getText()).doubleValue();


        equationCanvas.setDomain(domMaxx,domMinx,domMaxy,domMiny,strangeMo,domMaxt,domMint);




        equationCanvas.restart();

      } else if(arg.equals("Pausar")) {
        //equationCanvas.restart();
		if (porradobotao == false)
		porradobotao = true;
		else
		porradobotao = false;
		//equationCanvas.pausar();
      }//if(arg.equals("Reiniciar com novos parametros"))
      return(true);
    }//if(evt.target instanceof Button) 
    return(false);
  }//public boolean action(Event evt, Object arg)
  public void readFile(){
	String line;
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
	    strBuff.append(line + "  XX\n");
      }
      double a = 0.11;
      String aString = Double.toString(a);
      String MeuString = "Alo, Mamae!";

      txtArea.append("Meu Duplo = " + aString + "\n\n");
      txtArea.append("Meu String = " + MeuString + "\n\n");
      txtArea.append("O Arquivo de nome: " + fileToRead + ", segue abaixo:" + "\n\n");
      txtArea.append(strBuff.toString());
	}
	catch(IOException e){
	  e.printStackTrace();
	}
  }//public void readFile()
}//public class DoubleWellApplet extends Applet implements Runnable


