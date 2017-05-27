# Debugging
import matplotlib.pyplot as plt
#from jpm_fns import display

import numpy as np
from astropy import log
from astropy import units as u
from astropy.io import fits
from astropy.time import Time, TimeDelta

from scipy import signal, ndimage



# So we have two things here to keep track of.  The 4 parameters that
# characterize the ND filter and the coordinates of the edges of the
# filter at a particular Y value.  Maybe the pos method could return
# either one, depending on whether or not a y coordinate is
# specified.  In that case, what I have as pos now should be
# measure_pos, or something.

def read_im(HDUList_im_or_fname=None):
    """Returns an astropy.fits.HDUList given a filename, image or HDUList"""
    if HDUList_im_or_fname is None:
        log.info('No error, just saying that you have no image.')
    # --> These should potentially be issubclass
    elif isinstance(HDUList_im_or_fname, fits.HDUList):
        HDUList = HDUList_im_or_fname
    elif isinstance(HDUList_im_or_fname, np.ndarray):
        hdu = fits.PrimaryHDU(HDUList_im_or_fname)
        HDUList = fits.HDUList(hdu)
    elif isinstance(HDUList_im_or_fname, str):
        fname = HDUList_im_or_fname
        HDUList = fits.open(fname)
        H.close()
    else:
        raise ValueError('Not a valid input, HDUList_im_or_fname')
    return(HDUList)

def hist_of_im(im):
    """Returns histogram of image and index into centers of bins"""
    
    # Code from west_aux.py, maskgen.

    # Histogram bin size should be related to readnoise
    readnoise = 5
    hrange = (im.min(), im.max())
    nbins = int((hrange[1] - hrange[0]) / readnoise)
    hist, edges = np.histogram(im, bins=nbins,
                               range=hrange, density=True)
    # Convert edges of histogram bins to centers
    centers = (edges[0:-1] + edges[1:])/2
    #plt.plot(centers, hist)
    #plt.show()

    return(hist, centers)

class GetObjectCenterPix(HDUList_im_or_fname=None):
    """Base class for containing objects which calculate center pixel of an object and desired """

class NDData:
    """Neutral Density Data storage object"""

    def __init__(self, HDUList_im_or_fname=None):

        self.fname = None
        self.im = None
        # The shape of im is really all we need to store for
        # calculations, once we have the params
        self.im_shape = None
        self.params = None

        self.ingest_im(HDUList_im_or_fname)

        # ND filter position in case none is derivable from flats.  This is from:
        # print(nd_filt_pos('/data/io/IoIO/raw/2017-04-20/Sky_Flat-0007_Na_off-band.fit'))
        self.default_nd_pos = ((-7.35537190e-02,  -6.71900826e-02), 
                               (1.24290909e+03,   1.34830909e+03))

        # And we can refine it further for a good Jupiter example
        #print(nd_filt_pos('/data/io/IoIO/raw/2017-04-20/IPT-0045_off-band.fit',
        #                  initial_try=((-7.35537190e-02,  -6.71900826e-02), 
        #                               (1.24290909e+03,   1.34830909e+03))))
        self.default_nd_pos = ((-6.57640346e-02,  -5.77888855e-02),
                               (1.23532221e+03,   1.34183584e+03))
        self.n_y_steps = 15
        self.x_filt_width = 25
        self.edge_mask = 5
        self.max_movement=50
        self.max_delta_pix=10

    def ingest_im(self, HDUList_im_or_fname=None):
        """Returns image, reading from fname, if necessary"""
        self.HDUList = read_im(HDUList_im_or_fname)
        self.im = np.asfarray(self.HDUList[0].data)
        self.im_shape = self.im.shape
        h = self.HDUList[0].header
        if not h.get('NDPAR') is None:
            # Note transpose, since we are working in C!
            params[0,0] = h['NDPAR00']
            params[1,0] = h['NDPAR01']
            params[0,1] = h['NDPAR10']
            params[1,1] = h['NDPAR11']

            log.info('-->Write code to read the NDPAR FITS keys and put it in self.params')

        return(self.im)

    def edges(self, y, external_params=None):
        """Returns x coords of ND filter edges at given y coordinate(s)"""
        if not external_params is None:
            params = external_params
        else:
            if self.params is None:
                self.get_params()
            params = self.params
        params = np.asarray(params)
        if np.asarray(y).size == 1:
            return(params[1,:] + params[0,:]*(y - self.im_shape[0]/2))
        es = []
        for this_y in y:
            es.append(params[1,:] + params[0,:]*(this_y - self.im_shape[0]/2))
        return(es)
        
    def get_params(self):
        """Returns parameters which characterize ND filter (currently 2 lines fir to edges)"""
        if not self.params is None:
            return(self.params)

        # If we made it here, we need to calculate params.  Take
        # n_y_steps and make profiles, take the gradient and absolute
        # value to spot the edges of the ND filter
        nd_edges = [] ; ypts = []
        y_bin = int(self.im_shape[0]/self.n_y_steps)
        yrange = np.arange(0, self.im_shape[0], y_bin)
        for ypt in yrange:
            subim = self.im[ypt:ypt+y_bin, :]
            profile = np.sum(subim, 0)
            smoothed_profile = signal.savgol_filter(profile, self.x_filt_width, 3)
            d = np.gradient(smoothed_profile, 3)
            s = np.abs(d)

            # https://blog.ytotech.com/2015/11/01/findpeaks-in-python/
            # points out same problem I had with with cwt.  It is too
            # sensitive to little peaks.  However, I can find the peaks
            # and just take the two largest ones
            peak_idx = signal.find_peaks_cwt(s, np.arange(5, 20), min_snr=2)
            # Need to change peak_idx into an array instead of a list for
            # indexing
            peak_idx = np.array(peak_idx)
            # If available, limit our search to the region max_movement
            # around initial_try.
            bounds = (0,s.size)
            if not self.default_nd_pos is None:
                bounds = self.edges(ypt, self.default_nd_pos) + np.asarray((-self.max_movement, self.max_movement))
                bounds = bounds.astype(int)
                goodc = np.where(np.logical_and(bounds[0] < peak_idx, peak_idx < bounds[1]))
                peak_idx = peak_idx[goodc]
                #print(peak_idx)
                #print(s[peak_idx])
                #plt.plot(s)
                #plt.show()
                if peak_idx.size < 2:
                    continue
    
            # Sort on value
            sorted_idx = np.argsort(s[peak_idx])
            # Unwrap
            peak_idx = peak_idx[sorted_idx]
    
            # Thow out if lower peak is too weak.  Use Carey Woodward's
            # trick of estimating the noise on the continuum To avoid
            # contamination, do this calc just over our desired interval
            ss = s[bounds[0]:bounds[1]]
    
            noise = np.std(ss[1:-1] - ss[0:-2])
            #print(noise)
            if s[peak_idx[-2]] < 3 * noise:
                #print("Rejected")
                continue
    
            # Find top two and put back in index order
            top_two = np.sort(peak_idx[-2:])
            # Accumulate in tuples
            nd_edges.append(top_two)
            ypts.append(ypt)
    
        nd_edges = np.asarray(nd_edges)
        ypts = np.asarray(ypts)
        if nd_edges.size < 2:
            if self.default_nd_pos is None:
                raise ValueError('Not able to find ND filter position')
            log.warning('Unable to improve filter position over initial guess')
            return(self.default_nd_pos)
        
        #plt.plot(ypts, nd_edges)
        #plt.show()
    
        # Fit lines to our points, making the origin the center of the image in Y
        params = np.polyfit(ypts-self.im_shape[0]/2, nd_edges, 1)
        params = np.asarray(params)
        
        # Check to see if there are any bad points, removing them and
        # refitting
        resid = nd_edges - self.edges(ypts, params)
        # Do this one side at a time, since the points might not be on
        # the same y level and it is not easy to zipper the coordinate
        # tuple apart in Python
        goodc0 = np.where(abs(resid[:,0]) < self.max_delta_pix)
        goodc1 = np.where(abs(resid[:,1]) < self.max_delta_pix)
        #print(ypts[goodc1]-self.im_shape[0]/2)
        #print(nd_edges[goodc1, 1])
        if len(goodc0) < resid.shape[1]:
            params[:,0] = np.polyfit(ypts[goodc0]-self.im_shape[0]/2,
                                     nd_edges[goodc0, 0][0], 1)
        if len(goodc1) < resid.shape[1]:
            params[:,1] = np.polyfit(ypts[goodc1]-self.im_shape[0]/2,
                                     nd_edges[goodc1, 1][0], 1)
        #print(params)
        # Check parallelism by calculating shift of ends relative to each other
        dp = abs((params[0,1] - params[0,0]) * self.im_shape[0]/2)
        if dp > self.max_delta_pix:
            txt = 'ND filter edges are not parallel.  Edges are off by ' + str(dp) + ' pixels.'
            # DEBUGGING
            print(txt)
            plt.plot(ypts, nd_edges)
            plt.show()
    
            if self.default_nd_pos is None:
                raise ValueError(txt)
            log.warning(txt + ' Returning initial try.')
            params = self.default_nd_pos

        self.params = params
        # The HDUList headers are objects, so we can do this
        # assignment and the original object property gets modified
        h = self.HDUList[0].header
        # Note transpose, since we are working in C!
        h['NDPAR00'] = (params[0,0], 'ND filt left side slope at Y center of im')
        h['NDPAR01'] = (params[1,0], 'ND filt left side offset at Y center of im')
        h['NDPAR10'] = (params[0,1], 'ND filt right side slope at Y center of im')
        h['NDPAR11'] = (params[1,1], 'ND filt right side offset at Y center of im')

        #print(self.params)
        return(self.params)

    def coords(self):
        """Returns coordinates of ND filter in im given an ND_filt_pos"""
        if self.params is None:
            self.get_params()
        
        xs = [] ; ys = []
        for iy in np.arange(0, self.im_shape[0]):
            bounds = self.params[1,:] + self.params[0,:]*(iy - self.im_shape[0]/2) + np.asarray((self.edge_mask, -self.edge_mask))
            bounds = bounds.astype(int)
            for ix in np.arange(bounds[0], bounds[1]):
                xs.append(ix)
                ys.append(iy)
    
        # NOTE C order and the fact that this is a tuple of tuples
        return((ys, xs))

    def imshow(self):
        if self.im is None:
            self.ingest_im()
        plt.imshow(self.im)
        plt.show()

    #def pos(self, default_nd_pos=self.default_nd_pos,):
        
    # Code provided by Daniel R. Morgenthaler, May 2017
    #
    #
        #This is a picture string. ^
    #
    #
    #    if nd_pos is None:
    #        print('These are 4 numbers and nd_pos is none.')
    def area(self, width_nd_pos, length_nd_pos, variable=True):
        if variable is False or variable is None:
            print('The area of the netral density filter is ' +
                  str(width_nd_pos * length_nd_pos) +  '.')
        elif variable is True:
            return(str(width_nd_pos * length_nd_pos))
        else:
            raiseValueError('Use True False or None in variable')
        
    def perimeter(self, width_nd_pos,  length_nd_pos, variable=True):
        if variable is False or variable is None:
            print('The perimeter of the netral density filter is ' +
                  str(width_nd_pos * 2 + 2 *  length_nd_pos) +  '.')
        elif variable is True:
            return(str(width_nd_pos * 2 + 2 *  length_nd_pos) +  '.')
        else:
            raiseValueError('Use True False or None in variable')
            
    def VS(self,v1,value1,v2,value2,v3,value3):
        v1=value1 ; v2=value2 ; v3=value3
        return(v1, v2, v3)


def get_jupiter_center(HDUList_im_or_fname, y=None):
    """Returns two vectors, the center of Jupiter (whether or not Jupiter
    is on ND filter) and the desired position of Jupiter, assuming we
    want it to be centered on the ND filter at a postion y.  If y not
    specified, y center of image is used."""

    HDUList = read_im(HDUList_im_or_fname)
    im = HDUList[0].data
    
    if y is None:
        y = im.shape[0]/2
    # Get our neutral density filter object
    ND = NDData(im)
    ND_center = (np.average(ND.edges(y)), y)
    
    # Use the histogram technique to spot the bias level of the image.
    # The coronagraph creates a margin of un-illuminated pixels on the
    # CCD.  These are great for estimating the bias and scattered
    # light for spontanous subtraction.  The ND filter provides a
    # similar peak after bias subutraction (or, rather, it is the
    # second such peak)
    im_hist, im_hist_centers = hist_of_im(im)
    im_peak_idx = signal.find_peaks_cwt(im_hist, np.arange(10, 50))
    im -= im_hist_centers[im_peak_idx[0]]

    # Check to see if Jupiter is sticking out significantly from
    # behind the ND filter, in which case we are better off just using
    # the center of mass of the image and calling that good enough
    #print(np.sum(im))
    if np.sum(im) > 1E9: 
        y_x = ndimage.measurements.center_of_mass(im)
        return(y_x[::-1], ND_center)

    # Get the coordinates of the ND filter
    NDc = ND.coords()

    # Filter those by ones that are at least 1 std above the median
    boostc = np.where(im[NDc] > (np.median(im[NDc]) + np.std(im[NDc])))
    boost_NDc0 = np.asarray(NDc[0])[boostc]
    boost_NDc1 = np.asarray(NDc[1])[boostc]
    # Here is where we boost what is sure to be Jupiter, if Jupiter is
    # in the ND filter
    im[boost_NDc0, boost_NDc1] *= 1000
    y_x = ndimage.measurements.center_of_mass(im)
    #print(y_x[::-1])
    #plt.imshow(im)
    #plt.show()
    return(y_x[::-1], ND_center)

def guide_calc(x1, y1, fits_t1=None, x2=None, y2=None, fits_t2=None, guide_dt=10, guide_dx=0, guide_dy=0, last_guide=None, aggressiveness=0.5, target_c = np.asarray((1297, 1100))):
    """ Calculate offset guider values given pixel and times"""

    # Pixel scales in arcsec/pix
    main_scale = 1.59/2
    guide_scale = 4.42
    typical_expo = 385 * u.s
    
    if last_guide == None:
        guide_dt = guide_dt * u.s
        previous_dc_dt = np.asarray((guide_dx, guide_dy)) / guide_dt
    else:
        guide_dt = last_guide[0]
        previous_dc_dt = np.asarray((last_guide[1], last_guide[2])) / guide_dt

    # Convert input time interval to proper units
    
    # time period to use in offset guide file
    new_guide_dt = 10 * u.s

    if fits_t1 == None:
        t1 = Time('2017-01-01T00:00:00', format='fits')
    else:
        t1 = Time(fits_t1, format='fits')
    if fits_t2 == None:
        # Take our typical exposure time to settle toward the center
        t2 = t1 + typical_expo
    else:
        if fits_t1 == None:
            raise ValueError('fits_t1 given, but fits_t1 not supplied')
        t2 = Time(fits_t2, format='fits')
    dt = (t2 - t1) * 24*3600 * u.s / u.day

    c1 = np.asarray((x1, y1))
    c2 = np.asarray((x2, y2))
    
    if x2 == None and y2 == None:
        latest_c = c1
        measured_dc_dt = 0
    else:
        latest_c = c2
        measured_dc_dt = (c2 - c1) / dt * main_scale / guide_scale

    # Despite the motion of the previous_dc_dt, we are still getting
    # some motion form the measured_dc_dt.  We want to reverse that
    # motion and add in a little more to get to the target center.  Do
    # this gently over the time scale of our previous dt, moderated by
    # the aggressiveness
    
    target_c_dc_dt = (latest_c - target_c) / dt * aggressiveness
    print(target_c_dc_dt * dt)

    r = new_guide_dt * (previous_dc_dt - measured_dc_dt - target_c_dc_dt)
    
    # Print out new_rates
    print('{0} {1:+.3f} {2:+.3f}'.format(new_guide_dt/u.s, r[0], r[1]))

    return(new_guide_dt, r[0], r[1])

# These are needed for MaxImData
import win32com.client
import time

class MaxImData():
    """Stores data related to controlling MaxIm DL via ActiveX/COM events.

    Notes: 

    MaxIm camera, guide camera, and telescope must be set up properly
    first (e.g. you have used the setup for interactive observations).
    Even so, the first time this is run, keep an eye out for MaxIm
    dialogs, as this program will hang until they are answered.  To
    fix this, a wathdog timer would need to be used.

    Technical note for downstreeam object use: we don't have access to
    the MaxIm CCDCamera.ImageArray, but we do have access to similar
    information (and FITS keys) in the Document object.  The CCDCamera
    object is linked to the actual last image read, where the Document
    object is linked to the currently active window.  This means the
    calling routine could potentially expect the last image read in
    but instead get the image currently under focus by the user.  The
    solution to this is to (carefully) use notify events to interrupt
    MaxIm precisely when the event you expect happens (e.g. exposure
    or guide image acuired).  Then you are sure the Document object
    has the info you expect.  Beware that while you have control,
    MaxIm is stuck and back things may happen, like the guider might
    get lost, etc.  If your program is going to take a long time to
    work with the information it just got, figure out a way to do so
    asynchronously

    """

    def __init__(self):
        # Create containers for all of the objects that can be
        # returned by MaxIm.  We'll only populate them when we need
        # them.  Some of these we may never use or write code for
        self.Application = None
        self.CCDCamera = None
        self.Document = None
        # There is no convenient way to get the FITS header from MaxIm
        # unless we write the file and read it in.  Instead allow for
        # getting a selection of FITS keys to pass around in a
        # standard astropy fits HDUList
        self.FITS_keys = None
        self.HDUList = None
        self.required_FITS_keys = ('DATE-OBS', 'EXPTIME', 'EXPOSURE', 'XBINNING', 'YBINNING', 'XORGSUBF', 'YORGSUBF', 'FILTER', 'IMAGETYP', 'OBJECT')

        # Maxim doesn't expose the results of this menu item from the
        # Guider Settings Advanced tab in the object.  It's for
        # 'scopes that let you push both RA and DEC buttons at once
        # for guider movement
        self.simultaneous_guide_corrections = False
        # We can use the CCDCamera.GuiderMaxMove[XY] property for an
        # indication of how long it is safe to press the guider
        # movement buttons
        self.guider_max_move_multiplier = 20

        # The conversion between guider button push time and guider
        # pixels is stored in the CCDCamera.Guider[XY]Speed
        # properties.  Plate scales in arcsec/pix are not, though they
        # can be greped out of FITS headers. 

        # Main camera plate solve, binned 2x2:
        # RA 12h 55m 33.6s,  Dec +03° 27' 42.6"
        # Pos Angle +04° 34.7', FL 1178.9 mm, 1.59"/Pixel
        self.main_plate = 1.59/2 # arcsec/pix
        self.main_angle = 4.578333333333333 # CCW from N on east side of pier

        # Guider (Binned 1x1)
        # RA 07h 39m 08.9s,  Dec +34° 34' 59.0"
        # Pos Angle +178° 09.5', FL 401.2 mm, 4.42"/Pixel
        self.guider_plate = 4.42
        self.guider_angle = 178+9.5/60 - 180

        # This is a function that returns two vectors, the current
        # center of the object in the main camera and the desired center 
        #self.get_object_center = None

    def getApplication(self):
        if not self.Application is None:
            return(True)
        try:
            self.Application = win32com.client.Dispatch("MaxIm.Application")
        except:
            raise EnvironmentError('Error creating MaxIM application object.  Is MaxIM installed?')
        # Catch any other weird errors
        return(isinstance(self.Application, win32com.client.CDispatch))
        
    def getCCDCamera(self):
        if not self.CCDCamera is None:
            return(True)
        try:
            self.CCDCamera = win32com.client.Dispatch("MaxIm.CCDCamera")
        except:
            raise EnvironmentError('Error creating CCDCamera object.  Is there a CCD Camera set up in MaxIm?')
        # Catch any other weird errors
        return(isinstance(self.CCDCamera, win32com.client.CDispatch))

    def getDocument(self):
        """Gets the document object of the current window"""
        # The CurrentDocument object gets refreshed when new images
        # are taken, so all we need is to make sure we are connected
        # to begin with
        if not self.Document is None:
            return(True)
        self.getApplication()
        try:
            self.Document = self.Application.CurrentDocument
        except:
            raise EnvironmentError('Error retrieving document object')
        # Catch any other weird errors
        return(isinstance(self.Document, win32com.client.CDispatch))

    def connect(self):
        """Link to telescope, CCD camera(s), filter wheels, etc."""
        self.getApplication()
        self.Application.TelescopeConnected = True
        if self.Application.TelescopeConnected == False:
            raise EnvironmentError('Link to telescope failed.  Is the power on to the mount?')
        self.getCCDCamera()
        self.CCDCamera.LinkEnabled = True
        if self.CCDCamera.LinkEnabled == False:
            raise EnvironmentError('Link to camera hardware failed.  Is the power on to the CCD (including any connection hardware such as USB hubs)?')

    def guider_move(self, ddec, dra, dec=None):
        """Moves the telescope using guider slews.  ddec, dra in
        arcsec.  NOTE ORDER OF COORDINATES: Y, X to conform to C
        ordering of FITS images """
        self.connect()
        if dec is None:
            dec = self.CCDCamera.GuiderDeclination
        # Change to rectangular tangential coordinates for small deltas
        dra = dra*np.cos(np.radians(dec))
        # The guider motion is calibrated in pixels per second, with
        # the guider angle applied separately.  We are just moving in
        # RA and DEC, so we don't need to worry about the guider angle
        dpix = np.asarray(([dra, ddec])) / self.guider_plate
        # Multiply by speed, which is in pix/sec
        dt = dpix / np.asarray((self.CCDCamera.GuiderXSpeed, self.CCDCamera.GuiderYSpeed))
        
        # Do a sanity check to make sure we are not moving too much
        max_t = (self.guider_max_move_multiplier *
                 np.asarray((self.CCDCamera.GuiderMaxMoveX, 
                             self.CCDCamera.GuiderMaxMoveY)))
            
        if np.any(np.abs(dt) > max_t):
            #print(str((dra, ddec)))
            #print(str(np.abs(dt)))
            log.warning('requested move of ' + str((dra, ddec)) + ' arcsec translates into move times of ' + str(np.abs(dt)) + ' seconds.  Limiting move in one or more axes to max t of ' + str(max_t))
            dt = np.minimum(max_t, abs(dt)) * np.sign(dt)
            
        log.info('Moving guider ' + str(dt))
        if dt[0] > 0:
            RA_success = self.CCDCamera.GuiderMove(0, dt[0])
        elif dt[0] < 0:
            RA_success = self.CCDCamera.GuiderMove(1, -dt[0])
        else:
            # No need to move
            RA_success = True
        # Wait until move completes if we can't push RA and DEC
        # buttons simultaneously
        while not self.simultaneous_guide_corrections and self.CCDCamera.GuiderMoving:
                time.sleep(0.1)
        if dt[1] > 0:
            DEC_success = self.CCDCamera.GuiderMove(2, dt[1])
        elif dt[1] < 0:
            DEC_success = self.CCDCamera.GuiderMove(3, -dt[1])
        else:
            # No need to move
            DEC_success = True
        while self.CCDCamera.GuiderMoving:
            time.sleep(0.1)
        return(RA_success and DEC_success)

    def rot(self, vec, theta):
        """Rotates vector counterclockwise by theta degrees IN A
        TRANSPOSED COORDINATE SYSTEM Y,X"""
        # This is just a standard rotation through theta on X, Y, but
        # when we transpose, theta gets inverted
        theta = -np.radians(theta)
        c, s = np.cos(theta), np.sin(theta)
        print(vec)
        print(theta, c, s)
        M = np.matrix([[c, -s], [s, c]])
        return(np.dot(M, vec))

    def calc_main_move(self, current_pos, desired_center=None):
        """Returns vector [ddec, dra] in arcsec to move scope to
        center object at current_pos, where the current_pos and
        desired_centers are vectors expressed in pixels on the main
        camera in the astropy FITS Pythonic order Y, X"""

        self.connect()
        if desired_center is None:
            desired_center = \
            np.asarray((self.CCDCamera.StartY + self.CCDCamera.NumY, 
                        self.CCDCamera.StartX + self.CCDCamera.NumX)) / 2.
        dpix = np.asarray(desired_center) - current_pos
        dpix = self.rot(dpix, self.main_angle)
        return(dpix * self.main_plate)

    def get_keys(self):
        """Gets list of self.required_FITS_keys from current image"""
        self.FITS_keys = []
        for k in self.required_FITS_keys:
            self.FITS_keys.append((k, self.Document.GetFITSKey(k)))
        
    # --> Not sure if FITS files get written by MaxIm before or after
    # --> they become Document property after a fresh read.  Could use
    # --> CCDCamera version, but this keeps it consistent
    def set_keys(self, keylist):
        """Write desired keys to current image FITS header"""
        if not getDocument():
            log.warning('Cannot get Document object, no FITS keys set')
            return(None)
        if self.HDUList is None:
            log.warning('Asked to set_keys, but no HDUList is empty')
            return(None)
            
        try:
            h = self.HDUList[0].header
            for k in keylist:
                if h.get(k):
                    # Not sure how to get documentation part written
                    self.Document.SetFITSKey(k, h[k])
        except:
            log.warning('Problem setting keys: ', sys.exc_info()[0])
            return(None)
            

    def get_im(self):
        """Puts current MaxIm image (the image with focus) into a FITS HDUList.  If an exposure is being taken or there is no image, the im array is set equal to None"""
        self.connect()
        # Clear out HDUList in case we fail
        self.HDUList = None
        if not self.CCDCamera.ImageReady:
            return(None) 
        # For some reason, we can't get at the image array or its FITS
        # header through CCDCamera.ImageArray, but we can through
        # Document.ImageArray
        if not self.getDocument():
            return(None)
        
        # Make sure we have an array to work with
        c_im = self.Document.ImageArray
        if c_im is None:
            return(None)
        
        # Create a basic FITS image out of this and copy in the FITS
        # keywords we want

        # TRANSPOSE ALERT.  Document.ImageArray returns a tuple of
        # tuples shaped just how you would want it for X, Y.  Since
        # Python is written in C, this is stored in memory in in "C
        # order," which is the transpose of how they were intended to
        # be written into a FITS file.  Since all the FITS stuff
        # assumes that we are reading/writing FORTRAN-ordered arrays
        # bytes from/to a C language, we need to transpose our array
        # here so that the FITS stuff has the bytes in the order it
        # expects.  This seems less prone to generating bugs than
        # making users remember what state of transpose they are in
        # when dealing with arrays generated here vs. data read in
        # from disk for debugging routines.  This is also faster than
        # writing to disk and re-reading, since the ndarray order='F'
        # doesn't actually do any movement of data in memory, it just
        # tells numpy how to interpret the order of indices.
        c_im = np.asarray(c_im)
        adata = c_im.flatten()#order='K')# already in C order in memory
        # The [::-1] reverses the indices
        adata = np.ndarray(shape=c_im.shape[::-1],
                           buffer=adata, order='F')
        
        hdu = fits.PrimaryHDU(adata)
        self.get_keys()
        for k in self.FITS_keys:
            hdu.header[k[0]] = k[1]
        self.HDUList = fits.HDUList(hdu)
        return(self.HDUList)        

    # This is a really crummy object finder, since it will be confused
    # by cosmic ray hits.  It is up to the user to define an object
    # center finder that suits them, for instance one that uses
    # PinPoint astrometry
    # NOTE: The return order of indices is astropy FITS Pythonic: Y, X
    def get_object_center_pix(self):
        if self.get_im() is None:
            log.warning('No image')
            return(None)
        im = self.HDUList[0].data
        return(np.unravel_index(np.argmax(im), im.shape))
    
    
    def center_object(self):
        if self.get_im() is None:
            log.warning('No image')
            return(None)

        #self.guider_move(self.calc_main_move(self.get_object_center_pix()))
        obj_c = get_jupiter_center(self.HDUList)
        print('jupiter center = ', obj_c)
        self.guider_move(self.calc_main_move(obj_c))


log.setLevel('INFO')

# Start MaxIm
print('Getting MaxImData object...')
M = MaxImData()
print('Done')
print('Getting MaxImData camera...')
M.getCCDCamera()
print('Done')
# Keep it alive for these experiments
M.CCDCamera.DisableAutoShutdown = True
#M.connect()
#print(M.calc_main_move((50,50)))
#print(M.guider_move(10000,20))
print('Getting object center...')
print(M.get_object_center_pix())
print('Done')
print('Centering Jupiter!')
M.center_object()
print('Done')
print(M.calc_main_move((50,50)))
print(M.rot((1,1), 45))
print(M.HDUList[0].header)
plt.imshow(M.HDUList[0].data)
plt.show()
# Kill MaxIm
#M = None

print('Getting jupiter center')
print(get_jupiter_center('/Users/jpmorgen/byted/xfr/2017-04-20/IPT-0032_off-band.fit'))

#print(get_jupiter_center('/data/io/IoIO/raw/2017-04-20/IPT-0032_off-band.fit'))
#print(get_jupiter_center('/data/io/IoIO/raw/2017-04-20/IPT-0033_off-band.fit'))
#print(get_jupiter_center('/data/io/IoIO/raw/2017-04-20/IPT-0034_off-band.fit'))
#print(get_jupiter_center('/data/io/IoIO/raw/2017-04-20/IPT-0035_off-band.fit'))
#print(get_jupiter_center('/data/io/IoIO/raw/2017-04-20/IPT-0036_off-band.fit'))
#print(get_jupiter_center('/data/io/IoIO/raw/2017-04-20/IPT-0037_off-band.fit'))
#print(get_jupiter_center('/data/io/IoIO/raw/2017-04-20/IPT-0038_off-band.fit'))
# 
#print(get_jupiter_center('/data/io/IoIO/raw/2017-04-20/IPT-0042_off-band.fit'))
#print(get_jupiter_center('/data/io/IoIO/raw/2017-04-20/IPT-0043_off-band.fit'))
#print(get_jupiter_center('/data/io/IoIO/raw/2017-04-20/IPT-0044_off-band.fit'))
#print(get_jupiter_center('/data/io/IoIO/raw/2017-04-20/IPT-0045_off-band.fit'))
#print(get_jupiter_center('/data/io/IoIO/raw/2017-04-20/IPT-0046_off-band.fit'))
#print(get_jupiter_center('/data/io/IoIO/raw/2017-04-20/IPT-0047_off-band.fit'))
#print(get_jupiter_center('/data/io/IoIO/raw/2017-04-20/IPT-0048_off-band.fit'))
# 
# print(nd_center('/data/io/IoIO/raw/2017-04-20/IPT-0032_off-band.fit'))
# print(nd_center('/data/io/IoIO/raw/2017-04-20/IPT-0033_off-band.fit'))
# print(nd_center('/data/io/IoIO/raw/2017-04-20/IPT-0034_off-band.fit'))
# print(nd_center('/data/io/IoIO/raw/2017-04-20/IPT-0035_off-band.fit'))
# print(nd_center('/data/io/IoIO/raw/2017-04-20/IPT-0036_off-band.fit'))
# print(nd_center('/data/io/IoIO/raw/2017-04-20/IPT-0037_off-band.fit'))
# print(nd_center('/data/io/IoIO/raw/2017-04-20/IPT-0038_off-band.fit'))
# 
# print(nd_center('/data/io/IoIO/raw/2017-04-20/IPT-0042_off-band.fit'))
# print(nd_center('/data/io/IoIO/raw/2017-04-20/IPT-0043_off-band.fit'))
# print(nd_center('/data/io/IoIO/raw/2017-04-20/IPT-0044_off-band.fit'))
# print(nd_center('/data/io/IoIO/raw/2017-04-20/IPT-0045_off-band.fit'))
# print(nd_center('/data/io/IoIO/raw/2017-04-20/IPT-0046_off-band.fit'))
# print(nd_center('/data/io/IoIO/raw/2017-04-20/IPT-0047_off-band.fit'))
# print(nd_center('/data/io/IoIO/raw/2017-04-20/IPT-0048_off-band.fit'))
#ND=NDData('/data/io/IoIO/raw/2017-04-20/IPT-0045_off-band.fit')
#print(ND.get_params())

#print(get_jupiter_center('/data/io/IoIO/raw/2017-04-20/IPT-0045_off-band.fit'))
