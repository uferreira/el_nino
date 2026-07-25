//=====================================================================
// File:DoubleWellCanvas.java
//
// Applied Math 303, Term Project
// Blair Fraser, 2303725
//=====================================================================

import java.awt.*;

public class DoubleWellCanvas extends Canvas {
  //===================================================================
  // Variables
  //
  //===================================================================
  private DoubleWell equation;
  private double domainxMax, domainxMin, domainyMax, domainyMin, domaintMin, porraw
  , oldWindowtPos, windowtPos, cocoy, MES;
  private int windowxPos, windowyPos;
  private int oldWindowxPos, oldWindowyPos, antes, depois, icont;
  private Image offScreenImage, XiXiImage;
  private Graphics offScreenGraphics, XiXiGraphics;
  private double meuPasso;

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
    resize(400,300);
    equation = new DoubleWell(0.0, 0.0, 0.0, 0.0);
  }

  //===================================================================
  // Accessors
  //
  //===================================================================
  public void setParams(double b, double meses, double F2, double w) {
    equation.setParams(b, meses, F2, w);
    porraw = w;
    MES = meses;
    offScreenImage = null;
    offScreenGraphics = null;
  }

  public void setInitialState(double t, double x, double y, double z) {
    equation.setInitialState(t, x, y, z);
  //  cocoy = y; NAO FUNCIONA
  }    

  public void setTimeStep(double step) {
    equation.setTimeStep(step);
    meuPasso = step;
  }

  //===================================================================
  // SetDomain
  //
  // Set the section of phase space that the plot will show.
  //===================================================================
  public void setDomain(double maxx, double minx, double maxy, double miny) {
    domainxMax = maxx;
    domainxMin = minx;
    domainyMax = maxy;
    domainyMin = miny;
  }

  public void PassaDados(double NstepSize,double NTempe[],double NdTdt[]) {
    equation.PassaDados(NstepSize,NTempe,NdTdt);  
  }

  //===================================================================
  // restart
  //
  // Restart the oscillator from the initial state.
  //===================================================================
  public void restart() {
    equation.reset();
    offScreenImage = null;
    windowxPos = mapxPoint(equation.getx());
    windowyPos = mapyPoint(equation.gety());
//    windowtPos = maptPoint(equation.getTime());
    windowtPos = (equation.getTime());
    oldWindowxPos = windowxPos;
    oldWindowyPos = windowyPos;
    oldWindowtPos = windowtPos;
    if ( oldWindowxPos >= 990 || windowxPos >= 990 ) return;
  }

  //===================================================================
  //  minimumSize: returns a minimum size for the canvas.
  //===================================================================
  public Dimension minimumSize() {
    return new Dimension(400,350);
  }

  //===================================================================
  //  preferedSize: returns a good size for the canvas.
  //===================================================================
  public Dimension preferredSize() {
    return new Dimension(600,600);
  }



  //===================================================================


  //===================================================================
  // increment
  //
  // Increment the double well oscillator, map the new point onto the
  // window.
  //===================================================================
  public void increment() {

    oldWindowxPos = windowxPos;
    oldWindowyPos = windowyPos;
    oldWindowtPos = windowtPos;
    equation.increment();
    windowxPos = mapxPoint(equation.getx());
    windowyPos = mapyPoint(equation.gety());
    cocoy = mapyCoco(equation.gety());

 //   windowtPos = maptPoint(equation.getTime());
   windowtPos = (equation.getTime());


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

    if ( oldWindowxPos >= 990 || windowxPos >= 990 ) return;
    
    
    g.setColor(Color.red);
    g.drawString( "Pausar",     100, 100 );
    g.drawString( "______",     100, 100 );
    g.drawString( "Apagar",     300, 100 );
	g.drawString( "______",     300, 100 );
    g.drawString( "Continuar",  500, 100 );
    g.drawString( "________",   500, 100 );
    g.setColor(Color.black);    
    // Tres cruzes negras centrais de referencia:                   //  +    +    + 
	g.drawString( "25°",   400, 135 );
	g.drawString( "|",   400, 150 );
    g.drawLine(mapxPoint(1.0)-5, mapyPoint(0.0)-0, mapxPoint(1.0)+5,  mapyPoint(0.0)-0);     //  .    .    - 
    g.drawLine(mapxPoint(1.0)-0,  mapyPoint(0.0)-5, mapxPoint(1.0)-0,  mapyPoint(0.0)+5);    //  .    .    |
	g.drawString( "19°",   200, 135 );
	g.drawString( "|",   200, 150 );
    g.drawLine(mapxPoint(-1.0)-5, mapyPoint(0.0)-0, mapxPoint(-1.0)+5,  mapyPoint(0.0)-0);   //  -    .    .
    g.drawLine(mapxPoint(-1.0)-0,  mapyPoint(0.0)-5, mapxPoint(-1.0)-0,  mapyPoint(0.0)+5);  //  |    .    .
    g.drawString( "22°",   300, 135 );
	g.drawString( "|",   300, 150 );
    g.drawLine(mapxPoint(0.0)-5, mapyPoint(0.0)-0, mapxPoint(0.0)+5,  mapyPoint(0.0)-0);     //  .    -    .
    g.drawLine(mapxPoint(0.0)-0,  mapyPoint(0.0)-5, mapxPoint(0.0)-0,  mapyPoint(0.0)+5);    //  .    |    .
    g.setColor(Color.green);
    g.drawLine(0,45, 600,  45); // Traça linha verde superior do gráfico da série temporal
    g.setColor(Color.black);
    icont = 0;
	double rcont = 0.;
    while ( icont <= 600)
      {
      g.drawLine(icont, 40, icont,  50); // Traços verticais por década na linha verde superior
	  rcont = rcont + (600./7.);
      icont = (int)(rcont);
      }
	g.setColor(Color.gray);  
	g.drawString( "1950",   0, 20 );
	g.setColor(Color.white); 
    g.drawString( "1960",  85, 20 );
	g.setColor(Color.yellow); 
    g.drawString( "1970", 171, 20 );
	g.setColor(Color.green); 
    g.drawString( "1980", 257, 20 );
	g.setColor(Color.red); 
    g.drawString( "1990", 343, 20 );
	g.setColor(Color.blue); 
    g.drawString( "2000", 429, 20 );
	g.setColor(Color.black); 
	g.drawString( "2010", 514, 20 );
	  
	  
    g.setColor(Color.red);
    if ( oldWindowtPos > windowtPos ) {oldWindowtPos = windowtPos;}
	// Série temporal vermelha superior:
    g.drawLine((int)(oldWindowtPos/7.), 75-(int)(oldWindowxPos/10.), (int)(windowtPos/7.), 75-(int)(oldWindowxPos/10.));

                                 g.setColor(Color.gray);   // 1950_
    if ( windowtPos > 10*12*5 )  g.setColor(Color.white);  // 1960_
    if ( windowtPos > 20*12*5 )  g.setColor(Color.yellow); // 1970_
    if ( windowtPos > 30*12*5 )  g.setColor(Color.green);  // 1980_
    if ( windowtPos > 40*12*5 )  g.setColor(Color.red);    // 1990_
    if ( windowtPos > 50*12*5 )  g.setColor(Color.blue);   // 2000_
	if ( windowtPos > 60*12*5 )  g.setColor(Color.black);  // 2010_
    if ( oldWindowxPos >= 990 || windowxPos >= 990 ) g.setColor(Color.black);   // PORRA!

    g.drawLine(oldWindowxPos, oldWindowyPos, windowxPos, windowyPos); // Traca a linha do grafico de fase
 

    antes =  (int)((oldWindowtPos/5. - (MES -1.))/12.);
    depois  = (int) ((windowtPos/5. - (MES -1.))/12.);

  if ( antes < depois ) {


   g.drawLine(windowxPos - 2, windowyPos, windowxPos + 2, windowyPos);
   g.drawLine(windowxPos, windowyPos - 2, windowxPos, windowyPos + 2);
   g.drawLine(windowxPos - 2, windowyPos-2, windowxPos + 2, windowyPos+2);
   g.drawLine(windowxPos+2, windowyPos + 2, windowxPos-2, windowyPos - 2);
    g.fillOval(windowxPos-2, windowyPos-2, 4, 4);  
    g.fillOval(windowxPos-3, windowyPos-3, 6, 6);  // Marca o mes de referencia



  }

  }


  //===================================================================
  // Mouse Down : what to do when the mouse is pressed, delete the
  // canvas, forcing it to be recreated, blank.
  //===================================================================
  //public boolean mouseDown(Event evt, int x, int y) {
  public boolean mouseUp(Event evt, int x, int y) { 
	if( x<200  )  equation.setTimeStep(0.0);
	if( (x>200 & x<400) )  offScreenImage = null;
	if( x>400 )  equation.setTimeStep(meuPasso);
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


  private int maptPoint(double t) {
    return((int)(t));
  }

  private double mapyCoco(double y) {
    return((double)(y));
  }

  private int mapyPoint(double y) {
    return((int)(-(y-domainyMax)
           /(domainyMax-domainyMin)*(double)size().height));
  }
}

