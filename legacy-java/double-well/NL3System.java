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

public abstract class NL3System {


  //===================================================================
  // Variables
  //
  // currentState: the vector containing current time, current xvalue,
  //   and the current yvalue.
  // step : the time step to increment by at each step.
  //===================================================================
  private Timed3dVector initialState;
  private Timed3dVector currentState;   
  private double step;  


  //===================================================================
  // Methods
  //
  //===================================================================

  //===================================================================
  // f, g and h
  //
  // The functions f, g and h of the system.
  //===================================================================
  protected abstract double f(double x, double y, double z, double t);
  protected abstract double g(double x, double y, double z, double t);
  protected abstract double h(double x, double y, double z, double t);


  //===================================================================
  // Default Constructor
  //
  // Create a non-linear system object with no initial values set.
  //===================================================================
  NL3System() { 
  //  step = 0.01; 
     step = 0.005;
    currentState = new Timed3dVector(); 
    initialState = new Timed3dVector();
  }


  //===================================================================
  // accessor methods
  //
  // Sets and returns the various variables in the NL3System object.  
  //===================================================================
  public void setTimeStep(double timeStep) { step = timeStep; }
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
    public void incrementX() {
 
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

      //----------------------------
      // Calculate k1x, k1y and k1z
      //----------------------------
      double tempt = t;
      double tempx = x;
      double tempy = y;
      double tempz = z;
      double k1x = step * f(tempx, tempy, tempz, tempt);
      double k1y = step * g(tempx, tempy, tempz, tempt);
      double k1z = step * h(tempx, tempy, tempz, tempt);

      //----------------------------
      // Calculate k2x, k2y and k2z
      //----------------------------
      tempt = t + step/4.0;
      tempx = x + k1x/4.0;
      tempy = y + k1y/4.0;
      tempz = z + k1z/4.0; 
      double k2x = step * f(tempx, tempy, tempz, tempt);
      double k2y = step * g(tempx, tempy, tempz, tempt);
      double k2z = step * h(tempx, tempy, tempz, tempt);

      //----------------------------
      // Calculate k3x, k3y and k3z
      //----------------------------
      tempt = t + (3.0/8.0)*step;
      tempx = x + (3.0/32.0)*k1x + (9.0/32.0)*k2x;
      tempy = y + (3.0/32.0)*k1y + (9.0/32.0)*k2y;
      tempz = z + (3.0/32.0)*k1z + (9.0/32.0)*k2z;
      double k3x = step * f(tempx, tempy, tempz, tempt);
      double k3y = step * g(tempx, tempy, tempz, tempt);
      double k3z = step * h(tempx, tempy, tempz, tempt);

      //----------------------------
      // Calculate k4x, k4y and k4z
      //----------------------------
      tempt = t + (12.0/13.0)*step;
      tempx = x + (1932.0/2197.0)*k1x - (7200.0/2197.0)*k2x 
              + (7296.0/2197.0)*k3x;
      tempy = y + (1932.0/2197.0)*k1y - (7200.0/2197.0)*k2y 
              + (7296.0/2197.0)*k3y;
      tempz = z + (1932.0/2197.0)*k1z - (7200.0/2197.0)*k2z 
              + (7296.0/2197.0)*k3z;
      double k4x = step * f(tempx, tempy, tempz, tempt);
      double k4y = step * g(tempx, tempy, tempz, tempt);
      double k4z = step * h(tempx, tempy, tempz, tempt);

      //----------------------------
      // Calculate k5x, k5y and k5z
      //----------------------------
      tempt = t + step;
      tempx = x + (439.0/216.0)*k1x - 8.0*k2x + (3680.0/513.0)*k3x 
              - (845.0/4104.0)*k4x;
      tempy = y + (439.0/216.0)*k1y - 8.0*k2y + (3680.0/513.0)*k3y 
              - (845.0/4104.0)*k4y;
      tempz = z + (439.0/216.0)*k1z - 8.0*k2z + (3680.0/513.0)*k3z 
              - (845.0/4104.0)*k4z;
      double k5x = step * f(tempx, tempy, tempz, tempt);
      double k5y = step * g(tempx, tempy, tempz, tempt);
      double k5z = step * h(tempx, tempy, tempz, tempt);

      //----------------------------
      // Calculate k6x, k6y and k6z
      //----------------------------
      tempt = t + step/2.0;
      tempx = x - (8.0/27.0)*k1x + 2.0*k2x - (3544.0/2565.0)*k3x 
              + (1859.0/4104.0)*k4x - (11.0/40.0)*k5x;
      tempy = y - (8.0/27.0)*k1y + 2.0*k2y - (3544.0/2565.0)*k3y 
              + (1859.0/4104.0)*k4y - (11.0/40.0)*k5y;
      tempz = z - (8.0/27.0)*k1z + 2.0*k2z - (3544.0/2565.0)*k3z 
              + (1859.0/4104.0)*k4z - (11.0/40.0)*k5z;
      double k6x = step * f(tempx, tempy, tempz, tempt);
      double k6y = step * g(tempx, tempy, tempz, tempt);
      double k6z = step * h(tempx, tempy, tempz, tempt);

      //-----------------------------------------------
      // Compute the next t, next x, y and z values,
      // with global error O(h^5).
      //-----------------------------------------------
      currentState.setx( x + (16.0/135.0)*k1x + (6656.0/12825.0)*k3x 
                        + (28561.0/56430.0)*k4x - (9.0/50.0)*k5x 
                        + (2.0/55.0)*k6x);

      currentState.sety( y + (16.0/135.0)*k1y + (6656.0/12825.0)*k3y 
                        + (28561.0/56430.0)*k4y - (9.0/50.0)*k5y 
                        + (2.0/55.0)*k6y);
 
      currentState.setz( z + (16.0/135.0)*k1z + (6656.0/12825.0)*k3z 
                        + (28561.0/56430.0)*k4z - (9.0/50.0)*k5z 
                        + (2.0/55.0)*k6z);
 
      currentState.setTime(currentState.getTime() + step);

    }


};
