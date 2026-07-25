//=====================================================================
// File:DoubleWellCanvas.java
//
// Applied Math 303, Term Project
// Blair Fraser, 2303725
//=====================================================================

import java.awt.*;
import java.io.*;
import java.lang.*;

public class DoubleWellCanvas extends Canvas {
  //===================================================================
  // Variables
  //
  //===================================================================
  private DoubleWell equation;
  private double domainxMax, domainxMin, domainyMax, domainyMin, domaintMin,
   domaintMax, porraw, cocoy, MES, oldWindowtPos, windowtPos,X,Y,Z,T,oldX,oldY,oldT;
  private double anual[], nanual[];

  private int windowxPos, windowyPos, windowTPos, oldicont,V,VA, Anos;
  private int oldWindowxPos, oldWindowyPos, oldWindowTPos, antes, depois, icont;
  private Image offScreenImage, XiXiImage;
  private Graphics offScreenGraphics, XiXiGraphics;
  private double XK0, XK1, XK2, XK3, XK4, XK5;
  private double VelhoStep;
  private String MeuTempo;


  //===================================================================
  // Methods
  //
  //===================================================================

  //===================================================================
  // Constructor
  //
  // Construct a lorenz canvas with all values set to zero.
  //===================================================================
  public DoubleWellCanvas() {
    super();
    resize(400,400);
    equation = new DoubleWell(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0);
  }

  //===================================================================
  // Accessors
  //
  //===================================================================
  public void setParams(double b, double K1, double K3, double FA, double FF, double FA2, double FF2, double w, double K0, double K2, double K4, double K5, double Passo) {
    equation.setParams(b, K1, K3, FA, FF, FA2, FF2, w, K0, K2, K4, K5, Passo);
    porraw = w;
    XK0 = K0;
    XK1 = K1;
    XK2 = K2;
    XK3 = K3;
    XK4 = K4;
    XK5 = K5;
    VelhoStep=Passo;

    offScreenImage = null;
    offScreenGraphics = null;
  }

  public void setInitialState(double t, double x, double y, double z) {
    equation.setInitialState(t, x, y, z);
  //  cocoy = y; NAO FUNCIONA
  }    

  public void setTimeStep(double step) {
    equation.setTimeStep(step);
  }

  //===================================================================
  // SetDomain
  //
  // Set the section of phase space that the plot will show.
  //===================================================================
  public void setDomain(double maxx, double minx, double maxy,
            double miny, double month, double maxt, double mint ) {
    domainxMax = maxx;
    domainxMin = minx;
    domainyMax = maxy;
    domainyMin = miny;
    MES = month;
    domaintMax = maxt;
    domaintMin = mint;

  }


  //===================================================================
  // restart
  //
  // Restart the oscillator from the initial state.
  //===================================================================
  public void restart() {
    equation.reset();
    offScreenImage = null;
    X = equation.getx();
    Y = equation.gety();
    T = equation.getTime();

    windowxPos = mapxPoint(X);
    windowyPos = mapyPoint(Y);
    windowTPos = maptPoint(T);
    windowtPos = (T);
    oldWindowxPos = windowxPos;
    oldWindowyPos = windowyPos;
    oldWindowtPos = windowtPos;
    oldWindowTPos = windowTPos;
    oldX = X;
    oldY = Y;
    oldT = T;

  }
  /*
    public void pausar() {

    oldWindowxPos = windowxPos;
    oldWindowyPos = windowyPos;
    oldWindowtPos = windowtPos;
    oldWindowTPos = windowTPos;
    oldX = X;
    oldY = Y;
    oldT = T;

    //equation.incrementX();
    X = equation.getx();
    Y = equation.gety();
    T = equation.getTime();

    windowxPos = mapxPoint(X);
    windowyPos = mapyPoint(Y);
    windowTPos = maptPoint(T);
    windowtPos = (T);

  }
  */

  //===================================================================
  //  minimumSize: returns a minimum size for the canvas.
  //===================================================================
  public Dimension minimumSize() {
    return new Dimension(400,400);
	//return new Dimension(700,700);
  }

  //===================================================================
  //  preferedSize: returns a good size for the canvas.
  //===================================================================
  public Dimension preferredSize() {
    return new Dimension(600,600);
	//return new Dimension(900,900);
  }



  //===================================================================


  //===================================================================
  // increment
  //
  // Increment the double well oscillator, map the new point onto the
  // window.
  //===================================================================
  public int incrementA() {

    oldWindowxPos = windowxPos;
    oldWindowyPos = windowyPos;
    oldWindowtPos = windowtPos;
    oldWindowTPos = windowTPos;
    oldX = X;
    oldY = Y;
    oldT = T;

    equation.incrementX();
    X = equation.getx();
    Y = equation.gety();
    T = equation.getTime();

    windowxPos = mapxPoint(X);
    windowyPos = mapyPoint(Y);
    windowTPos = maptPoint(T);
    windowtPos = (T);
    return(windowxPos);

  }


  //===================================================================
  // update
  //
  // Update method for double buffering animation.
  //===================================================================
  public void update(Graphics g) {
    if(offScreenImage == null) {
      offScreenImage = createImage(size().width, size().height);
      offScreenGraphics = offScreenImage.getGraphics();
   //   offScreenGraphics.setColor(getBackground());
    //  offScreenGraphics.setColor(Color.red);
     offScreenGraphics.setColor(Color.white);
      offScreenGraphics.fill3DRect(0, 0, size().width, size().height, false);
    } else {
      if(offScreenGraphics == null) {
        offScreenGraphics = offScreenImage.getGraphics();
      }
      paint(offScreenGraphics);
    }    

    g.drawImage(offScreenImage, 0, 0, this);
    if (windowxPos < 300 ) {
    g.setColor(Color.blue);}
    if (windowxPos > 300 ) {
    g.setColor(Color.red);}

    g.fillOval(windowxPos-5, mapyPoint(0.0)-5, 10, 10);
  } 

  //===================================================================
  // paint
  //
  // Paint method for the canvas.
  //===================================================================
  public void paint(Graphics g) {


    g.setColor(Color.black);
    g.drawLine(mapxPoint(1.0)-5, mapyPoint(0.0)-0, mapxPoint(1.0)+5,  mapyPoint(0.0)-0);
    g.drawLine(mapxPoint(1.0)-0,  mapyPoint(0.0)-5, mapxPoint(1.0)-0,  mapyPoint(0.0)+5);
    g.drawLine(mapxPoint(-1.0)-5, mapyPoint(0.0)-0, mapxPoint(-1.0)+5,  mapyPoint(0.0)-0);
    g.drawLine(mapxPoint(-1.0)-0,  mapyPoint(0.0)-5, mapxPoint(-1.0)-0,  mapyPoint(0.0)+5);
    g.drawLine(mapxPoint(0.0)-5, mapyPoint(0.0)-0, mapxPoint(0.0)+5,  mapyPoint(0.0)-0);
    g.drawLine(mapxPoint(0.0)-0,  mapyPoint(0.0)-5, mapxPoint(0.0)-0,  mapyPoint(0.0)+5);

    g.setColor(Color.green);
    g.drawLine(0,30, 600,  30);
	
	
	
  g.drawString( "anos:", 0, 10 );
  g.drawString( "10", 100, 10 );
  g.drawString( "20", 200, 10 );
  g.drawString( "30", 300, 10 );
  g.drawString( "40", 400, 10 );
  g.drawString( "50", 500, 10 );
  //Anos = Double.toInteger(windowtPos/12.e0); //Não reconhece Double.toInteger !
  Anos = (int)(windowtPos/12.e0);
  //MeuTempo = Integer.toString(Anos);
  //MeuTempo = Double.toString((int))int(windowtPos/12.e0));
  //g.drawString( "Tempo em X anos:  " + MeuTempo, 5, 450 );

    g.setColor(Color.blue);
	
	  g.drawString( "Tempo em anos:  " + Anos, 5, 500 );
	  //repaint(); //?????
	  g.drawString( "Tempo em anos:_______________" , 5, 500 );
	

    g.setColor(Color.black);
	
	
    icont = 0;
    while ( icont <= 600)
      {
      g.drawLine(icont, 25, icont,  35);
      icont = icont + 100;
      }
//  public double getK1() { return(K1); }
//  public double getK3() { return(K3); }

    g.setColor(Color.black);
    icont = 0;
    VA = 999999;
    while ( icont <= 600)
     {
      Z = ( (double)(icont) -300. )/100.;
      V = (int)( 400.*(XK0*Z + XK1*Z*Z/2. + XK2*Z*Z*Z/3. + XK3*Z*Z*Z*Z/4. +  
          XK4*Z*Z*Z*Z*Z/5. + XK5*Z*Z*Z*Z*Z*Z/6.) ) + 250;
      if( VA == 999999){ VA = V;}
      g.drawLine(icont-20, VA, icont, V );
      icont = icont + 20;
      VA = V;
      }




    g.setColor(Color.red);
    if ( oldWindowTPos > windowTPos ) {oldWindowTPos = windowTPos;}
    g.drawLine(oldWindowTPos, 30-(int)(10.*oldX), windowTPos, 30-(int)(10.*X));

//    if ( T < 12.*30. )
//      { 
//     icont = 0;
//      while ( icont < 12)
//        {
//        antes =  (int)(porraw*(oldT + 0.5 - icont+1)/(2*Math.PI));
//        depois  = (int) (porraw*(T + 0.5 - icont+1)/(2*Math.PI));
//        if ( antes < depois )
//          { 
//          anual[icont] = anual[icont] + X;
//          nanual[icont] = nanual[icont] + 1.;
//          }
//        icont++;
//        }
//      }
//    else
//      {
//      oldicont = (int)(oldT - (int)(oldT/12.)*12.);
//      icont = (int)(T - (int)(T/12.)*12.);
//      g.setColor(Color.blue);
//      g.drawLine( oldWindowTPos, 
//                  250-(int)(10.*(oldX-anual[oldicont]/nanual[oldicont])), 
//                  windowTPos, 
//                  250-(int)(10.*(X-anual[icont]/nanual[icont]))
//                );
//      }


  //  if ( windowxPos < 300 ) {
  //  g.setColor(getBackground());}
  //  if ( windowxPos > 300 ) {
 //   }

    g.setColor(Color.yellow);
    g.drawLine(oldWindowxPos, oldWindowyPos, windowxPos, windowyPos);



    antes =  (int)(porraw*(oldWindowtPos + 0.5 - MES)/(2*Math.PI));
    depois  = (int) (porraw*(windowtPos + 0.5 - MES)/(2*Math.PI));

  if ( antes < depois ) {
   g.setColor(Color.black);
   g.drawLine(windowxPos - 2, windowyPos, windowxPos + 2, windowyPos);
   g.drawLine(windowxPos, windowyPos - 2, windowxPos, windowyPos + 2);
   }
 
   //g.drawString( "Tempo em anos:  " + windowTPos/12, 5, 550 );

  }//public void paint(Graphics g)


  //===================================================================
  // Mouse Down : what to do when the mouse is pressed, delete the
  // canvas, forcing it to be recreated, blank.
  //===================================================================
//  public boolean mouseDown(Event evt, int x, int y) {
//    offScreenImage = null;
//    return(true);
//  }

//  public boolean mouseDown(Event evt, int x, int y) {
    public boolean mouseEnter(Event evt, int x, int y) {
      {
	  repaint();
      //equation.setTimeStep(0.0);
      }
    return(true);
    }
    public boolean mouseOut(Event evt, int x, int y) {
      {
      equation.setTimeStep(VelhoStep);
      }
    return(true);
    }
    public boolean mouseUp(Event evt, int x, int y) {
    if(x>0){
              if(x<600){
                        if(y>0){
                                  if(y<600){
                                            offScreenImage = null;
                                           }
                                  }
                       }
             }
      
    return(true);
  }

  //===================================================================
  // Mapping functions
  //
  // Map a point in phase space onto the window.
  //===================================================================
  private int mapxPoint(double x) {
    return((int)((x-domainxMin)
           /(domainxMax-domainxMin)*(double)size().width));
  }

  private int mapyPoint(double y) {
    return((int)(-(y-domainyMax)
           /(domainyMax-domainyMin)*(double)size().height));
  }

  private int maptPoint(double t) {
    return((int)(
         (
         (t-12.*domaintMin -(int)((t-12.*domaintMin)/(12.*(domaintMax-domaintMin)))*(12.*(domaintMax-domaintMin))
          )/(12.*(domaintMax-domaintMin))
          
         )
        *(double)size().width));

  }


}

