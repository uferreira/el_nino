//=====================================================================
// File: DoubleWell.java
//
// Applied Math 303, Term Project
// Blair Fraser, 2303725
//=====================================================================

//=====================================================================
// DoubleWell Class
//
//=====================================================================
public class DoubleWell extends NL3System {


  //===================================================================
  // Variables
  //
  // The initial settings of the system.
  // The parameters of the system, constants etc.
  //===================================================================
  private double b;
  private double F;
  private double F2;
  private double w;

//  //-----------------------------------------------
//  // The functions f(x,y,z), g(x,y,z) and h(x,y,z)
//  //-----------------------------------------------
//  protected double f(double x, double y, double z, double t)
//    { return(0.0 ); }
//
//  protected double g(double x, double y, double z, double t)
   // { return( F*Math.cos(w*t) - F2*Math.sin(2.0*w*t) - b*y*Math.abs(y) + x - x*x*x ); }
//      { return( 0.0 ); }
//
//  protected double h(double x, double y, double z, double t)
//    { return( 0.0 ); }


  //===================================================================
  // Methods
  // 
  //===================================================================

  //===================================================================
  // Constructor
  // 
  //===================================================================
  DoubleWell(double b, double F, double F2, double w) {
    super();
    setParams(b, F, F2, w);
  }


  //===================================================================
  // setParams
  //
  // Sets the parameters of the system.
  //===================================================================
  public void setParams(double b, double F, double F2, double w) {
    this.b = b;
    this.F = F;
    this.F2 = F2;
    this.w = w;
  }


  //===================================================================
  // accessor methods
  //
  // Return the parameter settings for the System.
  //===================================================================
  public double getb() { return(b); }
  public double getF() { return(F); }
  public double getF2() { return(F2); }
  public double getw() { return(w); }

};


