//=====================================================================
// File: Timed3dVector.java
//
// Applied Math 303, Term Project
// Blair Fraser, 2303725
//=====================================================================

//=====================================================================
// Timed3dVector
//
// A vector consisting of a time, an x,y and z value.
//=====================================================================

class Timed3dVector {
  //===================================================================
  // Variables
  //  
  // x : the x location of the node at time 'time'
  // y : the y location of the node at time 'time'
  // z : the z location of the node at time 'time'
  // t : the time variable
  //===================================================================
  private double x,y,z,t;

  //===================================================================
  // Methods
  // 
  //===================================================================

  //===================================================================
  // Constructors
  //===================================================================
  public Timed3dVector(double tt, double tx, double ty, double tz) { 
     t = tt; x = tx; y = ty; z = tz;
  }

  public Timed3dVector() { t = 0.0; x = 0.0; y = 0.0; z = 0.0;}

  //===================================================================
  // Accessor methods
  //
  //===================================================================
  public void setTime(double tt) { t = tt; }
  public void setx(double xx) { x = xx; }
  public void sety(double yy) { y = yy; }
  public void setz(double zz) { z = zz; }
  public double getTime() { return(t); }
  public double getx() { return(x); }
  public double gety() { return(y); }
  public double getz() { return(z); }
};

