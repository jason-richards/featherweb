import featherweb
import gc

app = featherweb.FeatherWeb()

@app.route('/hello')
def Hello(client):
    """ Say Jello! """
    response = featherweb.HTTPResponse(client)
    response.sendtext("Jello!")

@app.route('/example.py')
def ExamplePy(client):
    """ Serve a binary file. """
    response = featherweb.HTTPResponse(client)
    response.sendfile('/example.py')

def TimeoutCB():
    """ I'm bored.  What else needs to be done... """
    print("We came up for air.  May as well pick up the trash...")
    gc.collect()
    return True

app.run(callback=TimeoutCB)
