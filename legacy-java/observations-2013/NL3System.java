//=====================================================================
// File: NL3System.java
//
// Applied Math 303, Term Project
// Blair Fraser, 2303725
//=====================================================================

//=====================================================================
// 3 dimensional non-linear system Class
//
// This is a base class to track the motion of a particle goverened
// by the system of equations,
//
//        x' = f(x,y,z,t)
//        y' = g(x,y,z,t)
//        z' = h(x,y,z,t)
//
// where f, g and h are arbitrary functions to be defined in derived
// classes.  Incrementing the position is performed with a fifth 
// order Runge-Kutta-Feldberg method.
//=====================================================================
import java.lang.*;
// ftp://ftp.ncep.noaa.gov/pub/cpc/wd52dg/data/indices/sstoi.indices
public abstract class NL3System {
  //===================================================================
  // Variables
  //
  // currentState: the vector containing current time, current xvalue,
  //   and the current yvalue.
  // step : the time step to increment by at each step.
  //===================================================================
  int[][] a1 = 
  {                             //sva.2_filter_10_9_1856.1_2002.03.dat
  { 148, 167 }, // 1950, 10 
  { 181, 161 }, // 1950, 11 
  { 213, 151 }, // 1950, 12 
  { 242, 137 }, // 1950, 13 
  { 267, 119 }, // 1950, 14 
  { 289, 97 }, // 1950, 20 
  { 439, 130 }, // 2002, 20 
  { 464, 122 }, // 2002, 21 
  { 488, 116 }, // 2002, 22 
  { 511, 111 }, // 2002, 23 
  { 533, 108 }, // 2002, 24 
  { 555, 107 }, // 2002, 30 
  };//int[][] a1 =
  //===================================================================
  //  int[] a2;
  // a2 = a1;
  //  for(int i = 0; i < a2.length; i++)
  //    a2[i]++;
  //===================================================================
  private Timed3dVector initialState;
  private Timed3dVector currentState;   
  private double step; 
  private double YstepSize;
  private double[] YTempe = new double[10000];
  private double[] YdTdt  = new double[10000];
  
  //===================================================================
  // Methods
  //
  //===================================================================
  //===================================================================
  // f, g and h
  //
  // The functions f, g and h of the system.
  //===================================================================
  //  protected abstract double f(double x, double y, double z, double t);
  //  protected abstract double g(double x, double y, double z, double t);
  //  protected abstract double h(double x, double y, double z, double t);
  //===================================================================
  // Default Constructor
  //
  // Create a non-linear system object with no initial values set.
  //===================================================================
  NL3System() { 
    //step = 0.01; 
    // step = 0.005;
    //////////////////////////////step = 1.000000;
    //int meustep = 1;
    currentState = new Timed3dVector(); 
    initialState = new Timed3dVector();
  }
  //===================================================================
  // accessor methods
  //
  // Sets and returns the various variables in the NL3System object.  
  //===================================================================
  public void setTimeStep(double timeStep) { step = timeStep; }
  //public void setTimeStep(int meutep) { meustep = timeStep; }
  
    public void PassaDados(double XstepSize,double XTempe[], double XdTdt[]) {
	  YstepSize = XstepSize;
	  YTempe = XTempe;
	  YdTdt  = XdTdt;
	}
  
  public void setInitialState(double t, double x, double y, double z) {
    initialState.setTime(t);  currentState.setTime(t);
    initialState.setx(x);     currentState.setx(x);
    initialState.sety(y);     currentState.sety(y);
    initialState.setz(z);     currentState.setz(z);
  }
  public double getTime() { return(currentState.getTime()); }
  public double getx() { return(currentState.getx()); }
  public double gety() { return(currentState.gety()); }
  public double getz() { return(currentState.getz()); }
  public void reset() { 
    currentState.setTime(initialState.getTime());
    currentState.setx(initialState.getx());
    currentState.sety(initialState.gety());
    currentState.setz(initialState.getz());
  }
  //===================================================================
  // increment
  //
  // Calling this method increments the position from time to
  // time + timeStep.  The x, y, and z positions are updated by a
  // fifth order Runge-Kutta-Feldberg method performed on each
  // equation of the system seperatly.
  //
  //                  x' = f(x,y,z)
  //                  y' = g(x,y,z)
  //                  z' = h(x,y,z)
  //
  //===================================================================
  // final static int moves[] = {4, 0, 2, 6, 8, 1, 3, 5, 7};
  static int moves[] = {4, 0, 2, 6, 8, 1, 3, 5, 7};
  int i = 2;
  int mw = moves[i];
  public void increment() {
	//-----------------------------
	// Perform some routine checks
	//-----------------------------
	//if(step <= 0.0) step = 0.001;
    //-------------------------------
    // Start the Runge-Kutta solving
    //-------------------------------
    double x = currentState.getx();
    double y = currentState.gety();
    double z = currentState.getz();
    double t = currentState.getTime();
    //-----------------------------------------------
    // Compute the next t, next x, y and z values
    //coco = 0.01 * (double)a1[t][2];
    //double porra =  (double) a1[meustep][3];
    //double xixi = (double)a1[step][3];
    double xixi = mw;
	//step =1.0;
	///////////////////////////////////////step = YstepSize;
    double coco = 50.*step;
    int tttmax = (int) z;
    int ttt = (int) t;
    if (ttt >= tttmax-5 )  ttt = tttmax-5 ;
 //   double xxx = a1[ttt][0]/300.;
    double xxx = YTempe[ttt]/300.;	
//    double yyy = a1[ttt][1]/300.;
    double yyy = YdTdt[ttt]/300.;	
    //currentState.setx( xxx );
    //currentState.sety( yyy );
    currentState.setx( xxx );
    currentState.sety( yyy );
    currentState.setz( z );
    currentState.setTime(t + step);
    }//public void increment()
}//public abstract class NL3System
