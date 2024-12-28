# -*- coding: utf-8 -*-
# twoDistancesIntersectionPlugin.py  -  Wtyczka przecięcie dwóch odległości dla aplikacji QGIS napisana w języku python
#     początek         : 2023-07-18
#     wersja           : 1.0.17
#.....data wersji......: 2024-12-28
#     autor            : Szymon Kędziora

from qgis.core           import (QgsPointXY,QgsPoint,QgsCircle,QgsGeometry,QgsWkbTypes,
                                 QgsFeature,QgsMapLayerType)
from qgis.gui            import (QgsMapTool,QgsMapToolAdvancedDigitizing,
                                 QgsSnapIndicator,QgsVertexMarker,QgsMapCanvasItem,QgsMapToolEdit)
from qgis.PyQt.QtCore    import Qt,QSettings,QLocale,QPointF,QLine,QUrl
from qgis.PyQt.QtGui     import QColor,QIcon,QCursor,QPen,QPainter,QBrush,QPolygonF,QDesktopServices
from qgis.utils          import iface
from qgis.PyQt.QtWidgets import QAction,QMessageBox,QToolBar
import os.path

from math import nextafter,sqrt,fabs,inf,fsum,dist,nan
from decimal import *

class MyPens:
    TEMP     = QPen(QColor(127,127,127,150),QgsMapToolEdit.digitizingStrokeWidth(),Qt.DashLine)
    LOCKED   = QPen((QSettings().value('/digitizing/snap-color')).lighter(),QgsMapToolEdit.digitizingStrokeWidth(),Qt.DashLine)
    ACCEPTED = QPen(QSettings().value('/digitizing/snap-color'),QgsMapToolEdit.digitizingStrokeWidth(),Qt.DashLine)
    DIGITIZING=QPen(QgsMapToolEdit.digitizingStrokeColor(),QgsMapToolEdit.digitizingStrokeWidth(),Qt.SolidLine)
    POINTING=QPen(QgsMapToolEdit.digitizingFillColor(),QgsMapToolEdit.digitizingStrokeWidth()+1,Qt.DashLine)
    
class MyBrushes:
    DIGITIZING=QBrush(QgsMapToolEdit.digitizingFillColor())

class MyCircleItem(QgsMapCanvasItem):
    def __init__(self,canvas,pen:MyPens):
        super().__init__(canvas)
        self.canvas = canvas
        
        self.center=None
        self.r=0.0
        self.pen=pen
        self.pixCenter=None
        self.pixR=0.0
        
    def setR(self,r):
        self.r=r
        mupp = self.canvas.getCoordinateTransform().mapUnitsPerPixel()
        if (mupp==0):
            return
        self.pixR = self.r/mupp
    
    def setCenter(self,center):
        self.center=center
        self.pixCenter=self.toCanvasCoordinates(self.center)
    
    #Do not use print() here because you will get error QPainter not ended
    def paint(self,painter,option, widget):
        if self.pixCenter==None or self.pixR==0:
            return
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(self.pen)
        
        painter.drawEllipse(self.pixCenter,self.pixR,self.pixR)
        
    def updatePosition(self):
        if self.center==None or self.r==0:
            return
        mupp = self.canvas.getCoordinateTransform().mapUnitsPerPixel()
        if (mupp==0):
            return
        self.pixR = self.r/mupp
        self.pixCenter=self.toCanvasCoordinates(self.center)
        
class MyLineItem(QgsMapCanvasItem):
    def __init__(self,canvas,pen:MyPens,p1XY,p2XY):
        super().__init__(canvas)
        self.canvas = canvas
        
        self.p1XY=p1XY
        self.p2XY=p2XY
        self.pen=pen
        
        self.pixP1=self.toCanvasCoordinates(self.p1XY)
        self.pixP2=self.toCanvasCoordinates(self.p2XY)

    #Do not use print() here because you will get error QPainter not ended
    def paint(self,painter,option, widget):
        if self.pixP1==None or self.pixP2==None:
            return
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(self.pen)
        painter.drawLine(self.pixP1,self.pixP2)
        
    def updatePosition(self):
        self.pixP1=self.toCanvasCoordinates(self.p1XY)
        self.pixP2=self.toCanvasCoordinates(self.p2XY)


class MyPolylineItem(QgsMapCanvasItem):
    def __init__(self,canvas,pen:MyPens,mapPointsXY):
        super().__init__(canvas)
        
        self.pen=pen
        self.mapPointsXY=mapPointsXY
        self.pixPoints=[]
        for p in self.mapPointsXY:
            self.pixPoints.append(self.toCanvasCoordinates(p))
    
    #Do not use print() here because you will get error QPainter not ended
    def paint(self,painter,option, widget):
        if self.mapPointsXY==None:
            return
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(self.pen)
        painter.drawPolyline(QPolygonF(self.pixPoints))
        
    def updatePosition(self):
        self.pixPoints=[]
        for p in self.mapPointsXY:
            self.pixPoints.append(self.toCanvasCoordinates(p))

class MyPolygonItem(QgsMapCanvasItem):
    def __init__(self,canvas,pen:MyPens,brush,mapPointsXY):
        super().__init__(canvas)
        
        self.pen=pen
        self.brush=brush
        self.mapPointsXY=mapPointsXY
        self.pixPoints=[]
        for p in self.mapPointsXY:
            self.pixPoints.append(self.toCanvasCoordinates(p))
    
    #Do not use print() here because you will get error QPainter not ended
    def paint(self,painter,option, widget):
        if self.mapPointsXY==None:
            return
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(self.brush)
        painter.setPen(self.pen)
        painter.drawPolygon(QPolygonF(self.pixPoints))
        
    def updatePosition(self):
        self.pixPoints=[]
        for p in self.mapPointsXY:
            self.pixPoints.append(self.toCanvasCoordinates(p))



#To get the distance given by center point and distance number.
#The center point is defined by layer coordinates and map coordinates.
class DistanceCapture: 
    
    def __init__(self, canvas,cadDockWidget,layer):
        self.canvas = canvas
        self.cadDockWidget=cadDockWidget
        self.layer=layer
        self.tool=canvas.mapTool()

        self.layerPointXY=None
        self.mapPointXY=None
        self.distance=0.0
        
        self.capturing=False    #To handle cadCanvasMoveEvent
        self.mousePressed=False #To not read self.cadDockWidget.constraintDistance().value()
                                #on cadCanvasPressEvent.
        
        self.circleItem=MyCircleItem(self.canvas,MyPens.TEMP)
        
        #Create utility with instance of project snapping config
        self.snapper = self.canvas.snappingUtils()
        
        self.snapIndicator = QgsSnapIndicator(self.canvas)
        
        self.cadDockWidget.lockDistanceChanged.connect(self.lockDistanceChanged)
        self.isLocked=False
        
    def lockDistanceChanged(self,locked):
        if locked:
            self.isLocked=True
            self.circleItem.setVisible(False)
            if self.cadDockWidget.constraintDistance().value()<=0:
                iface.messageBar().pushWarning("Ostrzeżenie",'Odległość nie może być mniejsza lub równa 0.  \
                    Proszę podać wartość większą od zera albo nacisnąć Esc aby opuścić panel. Jeśli chcesz anulować \
                    wyznaczanie przecięcia naciśnij Esc drugi raz.')
        else:
            if self.isLocked==True:
                self.isLocked=False
                self.circleItem.setVisible(True)
                self.canvas.setFocus() #to get the focus out of the cadDockWidget
            
    def step1(self,e):
        #e.mapPoint() is set to e.mapPointMatch.point()
        #by self.snapIndicator.setMatch(e.mapPointMatch()) in cadCanvasMoveEvent
        self.layerPointXY=None
        self.mapPointXY=None
        self.distance=0.0
        #if cadDockWidget is enabled use it to get accurate coordinates from numbers
        if self.cadDockWidget!=None and self.cadDockWidget.cadEnabled():
            self.layerPointXY=QgsPointXY(self.cadDockWidget.currentPointLayerCoordinates(self.layer))
            self.mapPointXY,_=self.cadDockWidget.currentPoint()
        else:
            self.layerPointXY=self.tool.toLayerCoordinates(self.layer,e.mapPoint())
            self.mapPointXY=e.mapPoint()
        self.circleItem.setCenter(self.mapPointXY)
        self.circleItem.setR(0.0)
        self.circleItem.update()
        if self.layerPointXY!=None and self.mapPointXY!=None:
            self.capturing=True
        else:
            iface.messageBar().pushWarning("Ostrzeżenie","Transformacja współrzędnych nie jest możliwa")
            
    def step2(self,e):
        if self.cadDockWidget!=None and self.cadDockWidget.cadEnabled():
            #We read the distance from the cadDockWidget form
            #Don't read e.mapPoint() when the cadDockWidget is enabled
            #because it distance from cadDockWidget to e.mapPoint() != distance entered by user
            #in cadDockWidget form !!!!!
            self.distance=self.cadDockWidget.constraintDistance().value()
        else:
            self.distance=self.mapPointXY.distance(e.mapPoint())
        self.capturing=False
        
    def cadCanvasPressEvent(self,e):
        self.mousePressed=True
        if e.button()==Qt.LeftButton and self.distance==0:
            self.step1(e)
        if e.button()==Qt.RightButton and self.layerPointXY!=None and self.distance==0:
            self.step2(e)
            if self.distance==0: #Entered zero
                self.mapPointXY=None
                self.layerPointXY=None
                iface.messageBar().pushWarning('Ostrzeżenie','Odległość nie może być równa zeru. \
                    Spróbuj ponownie przez lewe kliknięcie albo naciśnij Esc aby anulować.')
        return self.layerPointXY,self.mapPointXY,self.distance
            
    def keyPressEvent(self,e):
        if e.key()==Qt.Key_Escape:
            return True
        return False
        
    def cadCanvasMoveEvent(self,e):
        self.snapIndicator.setMatch(e.mapPointMatch()) #needed if cadDockWidget is not active
                                                       #makes e.mapPoint()==e.mapPointMatch()
        if self.capturing:
            if self.mousePressed: #To not read self.cadDockWidget.constraintDistance().value()
                                  #on cadCanvasPressEvent.
                self.mousePressed=False
            else:
                if self.cadDockWidget!=None and self.cadDockWidget.cadEnabled():
                        self.circleItem.setR(self.cadDockWidget.constraintDistance().value())
                else:
                    self.circleItem.setR(self.mapPointXY.distance(e.mapPoint()))
            self.circleItem.update()

    def __del__(self):
        self.cadDockWidget.lockDistanceChanged.disconnect(self.lockDistanceChanged)
        self.snapIndicator=None
        self.snapper=None
        self.canvas.scene().removeItem(self.circleItem)
        self.circleItem=None
        self.cadDockWidget.clearPoints()
        
        
class TwoDistancesIntersection:
    def __init__(self, canvas,cadDockWidget):
        self.canvas = canvas
        self.cadDockWidget=cadDockWidget
        self.tool=canvas.mapTool()
        
        self.layerPointsXY:QgsPointXY=[] #Is needed to add points(features) on layer
        self.mapPointsXY:QgsPointXY=[]   #Is needed to draw items
                                         #and get an intersection
        self.distances:float=[]    #Is needed to get an intersection
        
        self.layer=self.canvas.currentLayer() #The layer where intersection (result) will be drawn
        
        self.m=None
        self.interMapPointXY1=None
        self.interMapPointXY2=None
        self.interMapPointXY=None
        
        self.distanceCapture1=None
        self.distanceCapture2=None
        
        self.circleItem1=MyCircleItem(self.canvas,MyPens.ACCEPTED)
        self.circleItem2=MyCircleItem(self.canvas,MyPens.ACCEPTED)
        self.pointMarker=None
        self.rubberBand1=None
        self.rubberBand2=None
        
        self.distanceCapture1=DistanceCapture(self.canvas,self.cadDockWidget,self.layer)
    
    def keyPressEvent(self,e):
        if self.distanceCapture1!=None:
            if self.distanceCapture1.keyPressEvent(e):
                return True
        if self.distanceCapture2!=None:
            if self.distanceCapture2.keyPressEvent(e):
                return True
        if self.interMapPointXY!=None and e.key()==Qt.Key_Escape:
            #Restore cadDockWidget
            if self.cadDockWidgetWasEnabled:
                self.cadDockWidget.enable()
            return True
        return False
        
    def closerPoint(self,point,point1,point2):
        d1=point.distance(point1)
        d2=point.distance(point2)
        if d1<d2:
            return point1
        if d1>=d2:
            return point2
    
    def widgetRemoved(self):
        self.circleItem1.hide()
        self.circleItem2.hide()
        iface.messageBar().widgetRemoved.disconnect(self.widgetRemoved)
        self.canvas.unsetMapTool(self.tool)
    
    def cadCanvasPressEvent(self,e):
        if self.distanceCapture1!=None:
            distance=0.0
            layerPointXY,mapPointXY,distance=self.distanceCapture1.cadCanvasPressEvent(e)
            if distance>0:
                self.circleItem1.setCenter(mapPointXY)
                self.circleItem1.setR(distance)
                self.circleItem1.update()
                
                self.distanceCapture1=None
                
                self.layerPointsXY.append(layerPointXY)
                self.mapPointsXY.append(mapPointXY)
                self.distances.append(distance)
                self.distanceCapture2=DistanceCapture(self.canvas,self.cadDockWidget,self.layer)

        if self.distanceCapture2!=None:
            distance=0
            layerPointXY,mapPointXY,distance=self.distanceCapture2.cadCanvasPressEvent(e)
            if distance>0:
                self.circleItem2.setCenter(mapPointXY)
                self.circleItem2.setR(distance)
                self.circleItem2.update()
                
                self.distanceCapture2=None
                self.layerPointsXY.append(layerPointXY)
                self.mapPointsXY.append(mapPointXY)
                self.distances.append(distance)
                
                #Calculate an intersection point for map points
                #because map crs may be different than layer crs
                self.m,l=\
                    circleCircleIntersections(self.mapPointsXY[0].x(),self.mapPointsXY[0].y(),self.distances[0],
                                              self.mapPointsXY[1].x(),self.mapPointsXY[1].y(),self.distances[1])
                
                # m - number of intersection map points
                if self.m==0:
                    iface.messageBar().pushWarning("Ostrzeżenie","Nie ma przecięcia")
                    iface.messageBar().widgetRemoved.connect(self.widgetRemoved)
                    return False
                if self.m==1:
                    self.circleItem1.hide()
                    self.circleItem2.hide()
                    self.addResultToLayer(QgsPointXY(l[0],l[1]))
                    return True
                if self.m==2:
                    self.circleItem1.hide()
                    self.circleItem2.hide()
                    
                    #Temporary disable cadDockWidget
                    self.cadDockWidgetWasEnabled=False
                    if self.cadDockWidget.cadEnabled():
                        self.cadDockWidgetWasEnabled=True
                        self.cadDockWidget.disable()
                        
                    self.interMapPointXY1=QgsPointXY(l[0],l[1])
                    self.interMapPointXY2=QgsPointXY(l[2],l[3])
                    self.interMapPointXY=self.closerPoint(e.mapPoint(),self.interMapPointXY1,self.interMapPointXY2)
                    
                    match self.layer.geometryType():
                        case QgsWkbTypes.PointGeometry:
                            self.pointMarker = QgsVertexMarker(self.canvas)
                            self.pointMarker.setColor(self.tool.digitizingStrokeColor())
                            self.pointMarker.setIconSize(8)
                            self.pointMarker.setIconType(QgsVertexMarker.ICON_CIRCLE)
                            self.pointMarker.setFillColor(self.tool.digitizingStrokeColor())
                            self.rubberBand1=MyPolylineItem(self.canvas,MyPens.TEMP,
                                                        [self.mapPointsXY[0],self.interMapPointXY1,self.mapPointsXY[1]])
                            self.rubberBand2=MyPolylineItem(self.canvas,MyPens.TEMP,
                                                        [self.mapPointsXY[0],self.interMapPointXY2,self.mapPointsXY[1]])
                        case QgsWkbTypes.LineGeometry:
                            self.rubberBand1=MyPolylineItem(self.canvas,MyPens.TEMP,
                                                        [self.mapPointsXY[0],self.interMapPointXY1,self.mapPointsXY[1]])
                            self.rubberBand2=MyPolylineItem(self.canvas,MyPens.TEMP,
                                                        [self.mapPointsXY[0],self.interMapPointXY2,self.mapPointsXY[1]])
                        case QgsWkbTypes.PolygonGeometry:
                            self.rubberBand1=MyPolygonItem(self.canvas,MyPens.TEMP,MyBrushes.DIGITIZING,
                                                        [self.mapPointsXY[0],self.interMapPointXY1,self.mapPointsXY[1]])
                            self.rubberBand2=MyPolygonItem(self.canvas,MyPens.TEMP,MyBrushes.DIGITIZING,
                                                        [self.mapPointsXY[0],self.interMapPointXY2,self.mapPointsXY[1]])
                        case _:
                            self.rubberBand1=MyPolylineItem(self.canvas,MyPens.TEMP,
                                                        [self.mapPointsXY[0],self.interMapPointXY1,self.mapPointsXY[1]])
                            self.rubberBand2=MyPolylineItem(self.canvas,MyPens.TEMP,
                                                        [self.mapPointsXY[0],self.interMapPointXY2,self.mapPointsXY[1]])
                    
                    self.cadCanvasMoveEvent(e)
                    
                if self.m==-1:
                    iface.messageBar().pushWarning("Ostrzeżenie","Nie można wykonać obliczeń. Zakres odległości albo pozycji został przekroczony.")
                    iface.messageBar().widgetRemoved.connect(self.widgetRemoved)
                    return False
                    
        if self.interMapPointXY!=None and e.button()==Qt.LeftButton:
            self.interMapPointXY=self.closerPoint(e.mapPoint(),self.interMapPointXY1,self.interMapPointXY2)
            if self.interMapPointXY!=None:
                #Restore cadDockWidget
                if self.cadDockWidgetWasEnabled:
                    self.cadDockWidget.enable()
   
                interLayerPoint=self.tool.toLayerCoordinates(self.layer,self.interMapPointXY)
                self.interMapPointXY=None
                self.addResultToLayer(interLayerPoint)
                return True
        return False
    
    def addResultToLayer(self,interLayerPoint):
        if self.layer.isEditable():
            #Result on point layer
            if self.layer.geometryType()==QgsWkbTypes.PointGeometry:
                geom=QgsGeometry.fromPointXY(QgsPointXY(interLayerPoint))
                feat=QgsFeature(self.layer.fields())
                feat.setGeometry(geom)
                self.layer.addFeature(feat) #addFeature before openFeatureForm
                if self.layer.fields().count()>0 and self.featureFormEnabled():
                    iface.openFeatureForm(self.layer,feat)
                
            #Result on line layer
            if self.layer.geometryType()==QgsWkbTypes.LineGeometry:
                
                geom1=QgsGeometry.fromPolylineXY([self.layerPointsXY[0],QgsPointXY(interLayerPoint)])
                feat1=QgsFeature(self.layer.fields())
                feat1.setGeometry(geom1)
                self.layer.addFeature(feat1) #addFeature before openFeatureForm
                if self.layer.fields().count()>0 and self.featureFormEnabled():
                    iface.openFeatureForm(self.layer,feat1)
                
                geom2=QgsGeometry.fromPolylineXY([self.layerPointsXY[1],QgsPointXY(interLayerPoint)])
                feat2=QgsFeature(self.layer.fields())
                feat2.setGeometry(geom2)
                self.layer.addFeature(feat2)
                if self.layer.fields().count()>0 and self.featureFormEnabled():
                    iface.openFeatureForm(self.layer,feat2)

            #Result on polygon layer
            if self.layer.geometryType()==QgsWkbTypes.PolygonGeometry:
                geom=QgsGeometry.fromPolygonXY([[self.layerPointsXY[0],QgsPointXY(interLayerPoint),
                                                     self.layerPointsXY[1]]])
                feat=QgsFeature(self.layer.fields())
                feat.setGeometry(geom)
                self.layer.addFeature(feat) #addFeature before openFeatureForm
                if self.layer.fields().count()>0 and self.featureFormEnabled():
                    iface.openFeatureForm(self.layer,feat)
        else:
            iface.messageBar().pushWarning("Ostrzeżenie","Warstwa jest nieedytowalna")
    
    def cadCanvasMoveEvent(self, e):
        if self.distanceCapture1!=None:
            self.distanceCapture1.cadCanvasMoveEvent(e)
        if self.distanceCapture2!=None:
            self.distanceCapture2.cadCanvasMoveEvent(e)
        if self.interMapPointXY!=None:
            self.interMapPointXY=self.closerPoint(e.mapPoint(),self.interMapPointXY1,self.interMapPointXY2)
            if self.m==2:
                match self.layer.geometryType():
                    case QgsWkbTypes.PointGeometry:
                        self.pointMarker.setCenter(self.interMapPointXY)
                        if self.interMapPointXY==self.interMapPointXY1:
                            self.rubberBand1.pen=MyPens.POINTING
                            self.rubberBand2.pen=MyPens.TEMP
                        else:
                            self.rubberBand1.pen=MyPens.TEMP
                            self.rubberBand2.pen=MyPens.POINTING
                    case QgsWkbTypes.PolygonGeometry:
                        if self.interMapPointXY==self.interMapPointXY1:
                            self.rubberBand2.stackBefore(self.rubberBand1)
                            self.rubberBand1.pen=MyPens.DIGITIZING
                            self.rubberBand1.brush=MyBrushes.DIGITIZING
                            self.rubberBand2.pen=MyPens.TEMP
                            self.rubberBand2.brush=Qt.NoBrush
                        else:
                            self.rubberBand1.stackBefore(self.rubberBand2) #rubberBand with digitizingPen
                                                                           #on rubberBand with MyPens.TEMP
                            self.rubberBand1.pen=MyPens.TEMP
                            self.rubberBand1.brush=Qt.NoBrush
                            self.rubberBand2.pen=MyPens.DIGITIZING
                            self.rubberBand2.brush=MyBrushes.DIGITIZING
                    case _: #QgsWkbTypes.LineGeometry
                        if self.interMapPointXY==self.interMapPointXY1:
                            self.rubberBand1.pen=MyPens.DIGITIZING
                            self.rubberBand2.pen=MyPens.TEMP
                        else:
                            self.rubberBand1.pen=MyPens.TEMP
                            self.rubberBand2.pen=MyPens.DIGITIZING
                
                self.rubberBand1.update()
                self.rubberBand2.update()
                
            
    def featureFormEnabled(self):
        #Check edit from settings for layer
        if self.layer.editFormConfig().suppress()==1:
            return False
        if self.layer.editFormConfig().suppress()==2:
            return True
        #If layer settings point to global settings check global settings for edit form
        return not QSettings().value('/digitizing/disable-enter-attribute-values-dialog', type=bool)
        
    def __del__(self):
        self.distanceCapture1=None
        self.distanceCapture2=None
        self.canvas.scene().removeItem(self.circleItem1)
        self.circleItem1=None
        self.canvas.scene().removeItem(self.circleItem2)
        self.circleItem2=None
        if self.rubberBand1!=None:
            self.canvas.scene().removeItem(self.rubberBand1)
            self.rubberBand1=None
        if self.rubberBand2!=None:
            self.canvas.scene().removeItem(self.rubberBand2)
            self.rubberBand2=None
        if self.pointMarker!=None:
            self.canvas.scene().removeItem(self.pointMarker)
            self.pointMarker=None
        
        self.cadDockWidget.clearPoints()
        iface.statusBarIface().clearMessage()
        
class TwoDistancesIntersectionPlugin(QgsMapToolAdvancedDigitizing):

    def __init__(self,iface):
        super().__init__(iface.mapCanvas(),iface.cadDockWidget())
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.cadDockWidget=iface.cadDockWidget()
        #It must be in class otherwise you will get
        #__file__ atribute will cause "NameError: name '__file__' is not defined"
        #when you run script in interpreter mode
        self.plugin_dir = os.path.dirname(__file__)
        
        #for a in iface.pluginToolBar().actions():
        #    if a.objectName()=='twoDistancesIntersection':
        #        iface.removeToolBarIcon(a)
        
    def initGui(self):
        icon = QIcon(f'{self.plugin_dir}/icon.png')
        self.myAction = QAction(icon,'Przecięcie dwóch odległości', self.iface.mainWindow())
        self.myAction.setObjectName('twoDistancesIntersection')
        self.myAction.setCheckable(True)
        self.myAction.triggered.connect(self.run)
        iface.addToolBarIcon(self.myAction)
        self.setAction(self.myAction)
        
        #Vector layers with connected slots
        self.vLs=[]
        self.setButtonAccess()
        iface.currentLayerChanged.connect(self.setButtonAccess)
        
    def unload(self):
        if self.isActive():
            self.deactivate()
        self.iface.removeToolBarIcon(self.myAction)
        self.iface.currentLayerChanged.disconnect(self.setButtonAccess)
        del self.myAction
        
    def enableAction(self):
        self.myAction.setEnabled(True)
        
    def disableAction(self):
        self.myAction.setEnabled(False)
        
    def setButtonAccess(self):
        layer=self.canvas.currentLayer()
        if layer!=None and layer.type()==QgsMapLayerType.VectorLayer\
           and layer.geometryType()!=QgsWkbTypes.NullGeometry:
            if layer.isEditable():
                self.enableAction()
            else:
                self.disableAction()
            if not layer in self.vLs:
                layer.editingStarted.connect(self.enableAction)
                layer.editingStopped.connect(self.disableAction)
                self.vLs.append(layer)
        else:
            self.disableAction()
            
    
    def keyPressEvent(self,e):
        if self.tDI.keyPressEvent(e):
            self.canvas.unsetMapTool(self)
    
    def cadCanvasPressEvent(self,e):
        if self.tDI.cadCanvasPressEvent(e):
            self.canvas.unsetMapTool(self)
    
    def cadCanvasMoveEvent(self, e):
        self.tDI.cadCanvasMoveEvent(e)
            
    def run(self):
        self.layer=self.canvas.currentLayer()
        if self.layer==None:
            iface.messageBar().pushWarning("Ostrzeżenie","Nie ma bieżącej warstwy")
            self.myAction.setChecked(False)
            return
        if not self.layer.isEditable() and self.layer.type()==QgsMapLayerType.VectorLayer:
            iface.messageBar().pushWarning("Ostrzeżenie","Bieżąca warstwa jest nieedytowalna")
            self.myAction.setChecked(False)
            return
        if not self.layer.type()==QgsMapLayerType.VectorLayer:
            iface.messageBar().pushWarning("Ostrzeżenie","Bieżąca warstwa nie jest warstwą wektorową")
            self.myAction.setChecked(False)
            return
        self.canvas.setMapTool(self)
        self.tDI=TwoDistancesIntersection(self.canvas,self.cadDockWidget)
    
    #Called on setMapTool
    def activate(self):
        QgsMapToolAdvancedDigitizing.activate(self)

    #Called on unsetMapTool
    def deactivate(self):
        #Delete TwoDistancesIntersection object
        self.tDI=None
        for layer in self.vLs:
            try: #a layer can be deleted and I do not know what else
                layer.editingStarted.disconnect(self.enableAction)
                layer.editingStopped.disconnect(self.disableAction)
            except:
                pass
        self.vLs=[]
        self.cadDockWidget.clearPoints()
        QgsMapToolAdvancedDigitizing.deactivate(self)
        self.deactivated.emit()

class E:
#Calculate error range for arithmetic operations
    def add(ex,ey):
        return (ex**2+ey**2).sqrt()
    
    def pow(x,n,ex):
        return abs(n*ex*x**(n-1))
        
    def mul(x,y,ex,ey):
        f=x*y
        return abs(f*((ex/x)**2+(ey/y)**2).sqrt())

def circleCircleIntersections(x1:float,y1:float,r1:float,x2:float,y2:float,r2:float):
#Transform second circle to line
#Decimal numbers

    #Calculate float spaces
    spx1=nextafter(abs(x1),inf)-abs(x1)
    spy1=nextafter(abs(y1),inf)-abs(y1)
    spr1=nextafter(r1,inf)-r1
    spx2=nextafter(abs(x2),inf)-abs(x2)
    spy2=nextafter(abs(y2),inf)-abs(y2)
    spr2=nextafter(r2,inf)-r2
    
    #Convert to Decimal
    #All calculations will be in Decimal
    x1=Decimal(x1)
    y1=Decimal(y1)
    r1=Decimal(r1)
    x2=Decimal(x2)
    y2=Decimal(y2)
    r2=Decimal(r2)
    ex1=Decimal(spx1)
    ey1=Decimal(spy1)
    er1=Decimal(spr1)
    ex2=Decimal(spx2)
    ey2=Decimal(spy2)
    er2=Decimal(spr2)
    
    #Can not calculate
    if r1<er2 or r2<er1:
        return (-1,[])
    
    #Move circles
    #Accume circle1 center to (0,0)
    #Circle2 center to ((x2-x1),(y2-y1))
    x2=x2-x1
    y2=y2-y1

    if (x2==0 and y2==0) or (-ex2<x2<ex2 and -ey2<y2<ey2): #The circles coincide
        return (0,[])
        
    #C1:x**2+y**2=r1**2
    #C2:(x-x2)**2+(y-y2)**2=r2**2
    #C1-C2:ax+by+c=0
    #Coefficients a,b,c:
    a=-2*x2
    b=-2*y2
    c=x2*x2+y2*y2+r1*r1-r2*r2
    ea=2*ex2
    eb=2*ey2
    ex2sq=E.pow(x2,2,ex2)
    ey2sq=E.pow(y2,2,ey2)
    er1sq=E.pow(r1,2,er1)
    er2sq=E.pow(r2,2,er2)
    ec=E.add(E.add(E.add(ex2sq,ey2sq),er1sq),er2sq)
    
    #Distance the closest point on line to origin coordinate system
    #d0=abs(c)/sqrt(a*a+b*b)

    #Vector (a,b) is perpendicular to the line ax+by+c=0`
    #Scale vector v to distancle l: v*l/length(v)
    #Scale vector (a,b) to distance d0: (a,b)*d0/length(a,b)
    dabsq=a*a+b*b
    edabsq=E.add(E.pow(a,2,ea),E.pow(b,2,eb))
    x0=-a*c/dabsq
    y0=-b*c/dabsq

    csq=c*c
    ecsq=E.pow(c,2,ec)
    r1sq=r1*r1
    EPS=E.add(ecsq,E.mul(r1sq,dabsq,er1sq,edabsq))

    
    #The d0 and r1 comparison is the intersection criterion
    if csq>r1sq*dabsq+EPS: #No intersection points
        return (0,[])
    else: #One intersection point
        if (csq-r1sq*dabsq).copy_abs()<=EPS:
            #Restore circles position
            return (1,[float(x0+x1),float(y0+y1)])
        else: #Two intersection points
            #Intersection points distance from (x0,y0)
            #d=(r1*r1-c*c/sqrt(a*a+b*b))
            dsq=r1sq-csq/dabsq
            m=(dsq/dabsq).sqrt()
            ax=x0+b*m
            bx=x0-b*m
            ay=y0-a*m
            by=y0+a*m
            return(2,[float(ax+x1),float(ay+y1),float(bx+x1),float(by+y1)])

