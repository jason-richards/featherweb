import featherweb
import gc

app = featherweb.FeatherWeb()

@app.route('/hello')
def Hello(request):
    """ Say Jello! """
    request.send("Jello!")

@app.route('/example.py')
def ExamplePy(request):
    """ Serve a binary file. """
    request.sendfile('/example.py')

def TimeoutCB():
    """ I'm bored.  What else needs to be done... """
    print("We came up for air.  May as well pick up the trash...")
    gc.collect()
    return True

app.run(callback=TimeoutCB)
