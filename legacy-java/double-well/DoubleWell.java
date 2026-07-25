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
  private double K1;
  private double K3;
  private double FA;
  private double FF;
  private double FA2;
  private double FF2;
  private double w;
  private double K0;
  private double K2;
  private double K4;
  private double K5;
  private double Passo;



// fileinputstream(system.in)


  //-----------------------------------------------
  // The functions f(x,y,z), g(x,y,z) and h(x,y,z)
  //-----------------------------------------------
  protected double f(double x, double y, double z, double t)
    { return( y ); }

  protected double g(double x, double y, double z, double t)
 //{ return( F*Math.cos(w*t) - F2*Math.sin(2.0*w*t) - b*y + x - x*x*x ); }
 //{ return( F*Math.cos(w*t + 1.868) - F2*Math.cos(2.0*w*t + 1.011) - b*y + 0.00856*x - 0.000547*x*x*x ); }
 //{ return(+ 0.00856*x - 0.000547*x*x*x - 0.2157*Math.cos(w*t) - 0.7044*Math.sin(w*t) + 0.1642*Math.cos(2.0*w*t) - 0.2624*Math.sin(2.0*w*t) - b*y ); }
 //  { return( FA*Math.cos(.523599*t) + FF*Math.sin(.523599*t) + FA2*Math.cos(2.0*.523599*t) + FF2*Math.sin(2.0*.523599*t) + b*y + K1*x +  K3*x*x*x ); }

 { 
return( K1*x +  K3*x*x*x + FA*Math.cos(FF*Math.PI/180.)*Math.cos(w*t) + FA*Math.sin(FF*Math.PI/180.)*Math.sin(w*t) + FA2*Math.cos(FF2*Math.PI/180.)*Math.cos(2.0*w*t) + FA2*Math.sin(FF2*Math.PI/180.)*Math.sin(2.0*w*t) + b*y + K0 + K2*x*x + K4*x*x*x*x + K5*x*x*x*x*x ); 
}


  protected double h(double x, double y, double z, double t)
    { return( 0.0 ); }


  //===================================================================
  // Methods
  // 
  //===================================================================

  //===================================================================
  // Constructor
  // 
  //===================================================================
  DoubleWell(double b, double K1, double K3, double FA, double FF, double FA2, double FF2, double w,  double K0, double K2, double K4, double K5, double Passo) {
    super();
    setParams(b, K1, K3, FA, FF, FA2, FF2, w, K0, K2, K4, K5, Passo);
  }


  //===================================================================
  // setParams
  //
  // Sets the parameters of the system.
  //===================================================================
  public void setParams(double b, double K1, double K3, double FA, double FF, double FA2, double FF2, double w,  double K0, double K2, double K4, double K5, double Passo) {
    this.b = b;
    this.K1 = K1;
    this.K3 = K3;
    this.FA = FA;
    this.FF = FF;
    this.FA2 = FA2;
    this.FF2 = FF2;
    this.w = w;
    this.K0 = K0;
    this.K2 = K2;
    this.K4 = K4;
    this.K5 = K5;
    this.Passo = Passo;

  }
  //===================================================================
  // accessor methods
  //
  // Return the parameter settings for the System.
  //===================================================================
  public double getb() { return(b); }
  public double getK1() { return(K1); }
  public double getK3() { return(K3); }

  public double getFA() { return(FA); }
  public double getFA2() { return(FA2); }
  public double getFF() { return(FF); }
  public double getFF2() { return(FF2); }
  public double getw() { return(w); }
  public double getK0() { return(K0); }
  public double getK2() { return(K2); }
  public double getK4() { return(K4); }
  public double getK5() { return(K5); }
  public double getPasso() { return(Passo); }

};


